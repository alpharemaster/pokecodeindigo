#ifndef POKEHEARTGOLD_NNSYS_SND_INTERNAL_H
#define POKEHEARTGOLD_NNSYS_SND_INTERNAL_H

// NitroSystem sound library: types and declarations the public nnsys/snd headers lack, shared by the
// lib/NitroSystem/src/snd_*.c modules (driver main loop, resource manager, wave out, sequence players,
// streams, capture effects).

#include <nitro.h>
#include <nnsys/fnd_internal.h>
#include <nnsys/snd.h>

// ---- NitroSDK functions the nitro headers do not declare

typedef struct PmSleepCallback {
    void (*func)(void *arg);
    void *arg;
    struct PmSleepCallback *next;
} PmSleepCallback;

void PM_PrependPreSleepCallback(PmSleepCallback *info);
void PM_AppendPostSleepCallback(PmSleepCallback *info);
void PM_DeletePreSleepCallback(PmSleepCallback *info);
void PM_DeletePostSleepCallback(PmSleepCallback *info);

#define SND_DRIVER_INFO_SIZE 0x11E0

typedef struct SndDriverInfo {
    u8 data[SND_DRIVER_INFO_SIZE];
} SndDriverInfo;

#define SND_CMD_FLAG_NOBLOCK 0x0
#define SND_CMD_FLAG_BLOCK   0x1

void SND_Init(void);
const void *SND_RecvCommandReply(u32 flags);
BOOL SND_FlushCommand(u32 flags);
void SND_WaitForCommandProc(u32 tag);
u32 SND_GetCurrentCommandTag(void);
BOOL SND_IsFinishedCommandTag(u32 tag);
void SND_ReadDriverInfo(SndDriverInfo *info);
BOOL SND_ReadChannelInfo(const SndDriverInfo *driverInfo, int chNo, SNDChannelInfo *chInfo);
BOOL SND_ReadTrackInfo(const SndDriverInfo *driverInfo, int playerNo, int trackNo, SNDTrackInfo *trackInfo);
u32 SND_GetPlayerStatus(void);
u16 SND_GetChannelStatus(void);
int SND_GetPlayerLocalVariable(u32 playerNo, int varNo);
u16 SND_CalcChannelVolume(s32 decibel);
void SND_SetMasterVolume(s32 volume);
void SND_SetMasterPan(s32 pan);
void SND_ResetMasterPan(void);
void SND_SetOutputSelector(s32 left, s32 right, s32 channel1, s32 channel3);
void SND_StartTimer(u32 chBitMask, u32 capBitMask, u32 alarmBitMask, u32 flags);
void SND_StopTimer(u32 chBitMask, u32 capBitMask, u32 alarmBitMask, u32 flags);
void SND_SetupAlarm(s32 alarmNo, u32 tick, u32 period, void (*callback)(void *arg), void *arg);
void SND_LockChannel(u32 chBitMask, u32 flags);
void SND_UnlockChannel(u32 chBitMask, u32 flags);
void SND_SetupChannelPcm(s32 chNo, s32 format, const void *data, s32 loopMode, s32 loopStart, s32 dataLen, s32 volume, s32 shift, s32 timer, s32 pan);
void SND_SetChannelTimer(u32 chBitMask, s32 timer);
void SND_SetChannelVolume(u32 chBitMask, s32 volume, s32 shift);
void SND_SetChannelPan(u32 chBitMask, s32 pan);
void SND_PrepareSeq(s32 playerNo, const void *seqBase, u32 seqOffset, void *bank);
void SND_StartPreparedSeq(s32 playerNo);
void SND_StopSeq(s32 playerNo);
void SND_PauseSeq(s32 playerNo, BOOL flag);
void SND_SetPlayerVolume(s32 playerNo, s32 volume);
void SND_SetPlayerTempoRatio(s32 playerNo, s32 ratio);
void SND_SetPlayerChannelPriority(s32 playerNo, s32 prio);
void SND_SetTrackPitch(s32 playerNo, u32 trackBitMask, s32 pitch);
void SND_SetTrackPan(s32 playerNo, u32 trackBitMask, s32 pan);
void SND_SetTrackAllocatableChannel(s32 playerNo, u32 trackBitMask, u32 chBitMask);

extern const s16 SNDi_DecibelTable[0x80]; // volume (0-127) -> decibel

// ---- fader (snd_fader.c)

typedef struct SndFader {
    s32 origin;
    s32 target;
    s32 counter;
    s32 frames;
} SndFader;

void NNSi_SndFaderInit(SndFader *fader);
void NNSi_SndFaderSet(SndFader *fader, s32 target, s32 frames);
s32 NNSi_SndFaderGet(SndFader *fader);
void NNSi_SndFaderUpdate(SndFader *fader);
BOOL NNSi_SndFaderIsFinished(SndFader *fader);

// ---- sound heap (snd_heap.c)

typedef void (*SndHeapDisposeCallback)(void *mem, u32 size, u32 data1, u32 data2);

void *NNS_SndHeapAlloc(NNSSndHeapHandle heap, u32 size, SndHeapDisposeCallback callback, u32 data1, u32 data2);
BOOL NNS_SndHeapClear(NNSSndHeapHandle heap);
void NNS_SndHeapDestroy(NNSSndHeapHandle heap);

// ---- initialization, main loop, sleep handlers, driver info (snd_system.c)

typedef struct SndMainState {
    s8 driverInfoIdx;   // driver info buffer last read, -1 before the first update
    BOOL isFirstUpdate; // the first NNS_SndUpdateDriverInfo only requests the driver info
    u32 driverInfoTag;  // command tag of the pending driver info request
    BOOL initialized;
    PmSleepCallback preSleep;
    PmSleepCallback postSleep;
} SndMainState;

extern SndMainState gSndMainState;
extern PmSleepCallback gSndMainPreSleepCallback;  // gSndMainState.preSleep
extern PmSleepCallback gSndMainPostSleepCallback; // gSndMainState.postSleep
extern SndDriverInfo gSndDriverInfo[2];

void NNS_SndSetMasterVolume(int volume);
void NNS_SndSetMonoFlag(BOOL flag);
BOOL NNSi_SndReadDriverTrackInfo(int playerNo, int trackNo, SNDTrackInfo *trackInfo);
void BeginSleep(void *arg);
void EndSleep(void *arg);

// ---- resource manager (snd_resource_mgr.c)

typedef struct SndResourceMgr {
    u32 lockedCaptures;
    u32 allocatedAlarms;
    u32 lockedChannels;
} SndResourceMgr;

extern SndResourceMgr gSndResourceMgr;

void NNSi_SndInitResourceMgr(void);
BOOL NNS_SndLockChannel(u32 chBitFlag);
void NNS_SndUnlockChannel(u32 chBitFlag);
void NNS_SndUnlockCapture(u32 capBitFlag);
int NNS_SndAllocAlarm(void);
void NNS_SndFreeAlarm(int alarmNo);

// ---- wave out (snd_waveout.c)

struct NNSSndWaveOut {
    u32 chNo;
    int sampleRate;
    BOOL isPlaying;
    BOOL isStarted; // the start command has been processed by the driver
    u32 startTag;
};

extern struct NNSSndWaveOut gSndWaveOuts[SND_CHANNEL_NUM];

NNSSndWaveOutHandle NNS_SndWaveOutAllocChannel(int chNo);
void NNS_SndWaveOutFreeChannel(NNSSndWaveOutHandle handle);
BOOL NNS_SndWaveOutStart(NNSSndWaveOutHandle handle, NNSSndWaveFormat format, const void *data, BOOL loopFlag, int loopStartSample, int samples, int sampleRate, int volume, int speed, int pan);
void NNS_SndWaveOutStop(NNSSndWaveOutHandle handle);
void NNS_SndWaveOutSetVolume(NNSSndWaveOutHandle handle, int volume);
void NNS_SndWaveOutSetSpeed(NNSSndWaveOutHandle handle, int speed);
void NNS_SndWaveOutSetPan(NNSSndWaveOutHandle handle, int pan);
BOOL NNS_SndWaveOutIsPlaying(NNSSndWaveOutHandle handle);

// ---- sequence players (snd_player.c)

#define SND_SEQ_PLAYER_NUM 16
#define SND_PLAYER_NUM     32

typedef struct SndPlayerInfo {
    NNSFndList playerList; // NNSSndSeqPlayer playing on this player, by priority
    NNSFndList heapList;   // free SndPlayerHeap of this player
    u32 playableSeqCount;
    u32 allocChBitFlag;
    u8 volume;
} SndPlayerInfo;

typedef struct SndPlayerHeap {
    NNSFndLink link;
    NNSSndHeapHandle heap;
    struct NNSSndSeqPlayer *player; // NULL while free
    int playerNo;
    u8 buffer[0];
} SndPlayerHeap;

enum {
    SND_SEQ_PLAYER_STATUS_FREE,
    SND_SEQ_PLAYER_STATUS_PLAY,
    SND_SEQ_PLAYER_STATUS_FADEOUT,
};

enum {
    SND_SEQ_TYPE_NONE,
    SND_SEQ_TYPE_SEQ,
    SND_SEQ_TYPE_SEQARC,
};

typedef struct NNSSndSeqPlayer {
    NNSSndHandle *handle;
    SndPlayerInfo *playerInfo;
    SndPlayerHeap *heap;
    NNSFndLink playerLink;
    NNSFndLink prioLink;
    SndFader fader;
    u8 status;    // SND_SEQ_PLAYER_STATUS_*
    u8 isStarted; // the prepare command has been processed by the driver
    u8 isPaused;
    u8 isPrepared; // prepared, start pending
    u32 prepareTag;
    u16 seqType; // SND_SEQ_TYPE_*
    u16 unk_36;
    u16 seqNo; // seqarc number for SND_SEQ_TYPE_SEQARC
    u16 seqArcIdx;
    u8 playerNo; // driver player
    u8 priority;
    s16 volume; // decibel last sent to the driver
    u8 initVolume;
    u8 extVolume;
} NNSSndSeqPlayer;

// The NNS_SndPlayer* functions read NNSSndHandle.player through a volatile view (the sequence player
// clears it when it shuts down); needed for the match.
#define SND_HANDLE_PLAYER(handle) (*(NNSSndSeqPlayer *volatile *)&(handle)->player)

extern NNSFndList gSndFreeSeqPlayerList;
extern NNSFndList gSndSeqPlayerPrioList;
extern NNSSndSeqPlayer gSndSeqPlayers[SND_SEQ_PLAYER_NUM];
extern SndPlayerInfo gSndPlayerInfo[SND_PLAYER_NUM];

// separate labels at members of gSndPlayerInfo[0] (the pieces address them that way)
typedef struct SndPlayerInfoU16View {
    u16 value;
    u8 rest[sizeof(SndPlayerInfo) - sizeof(u16)];
} SndPlayerInfoU16View;

typedef struct SndPlayerInfoU32View {
    u32 value;
    u8 rest[sizeof(SndPlayerInfo) - sizeof(u32)];
} SndPlayerInfoU32View;

typedef struct SndPlayerInfoU8View {
    u8 value;
    u8 rest[sizeof(SndPlayerInfo) - sizeof(u8)];
} SndPlayerInfoU8View;

extern SndPlayerInfoU16View gSndPlayerInfoNumPlaying[];       // gSndPlayerInfo[i].playerList.numObjects
extern SndPlayerInfoU32View gSndPlayerInfoPlayableSeqCount[]; // gSndPlayerInfo[i].playableSeqCount
extern SndPlayerInfoU32View gSndPlayerInfoAllocChBitFlag[];   // gSndPlayerInfo[i].allocChBitFlag
extern SndPlayerInfoU8View gSndPlayerInfoVolume[];            // gSndPlayerInfo[i].volume

void NNSi_SndPlayerInit(void);
void NNSi_SndPlayerMain(void);
NNSSndSeqPlayer *NNSi_SndPlayerAllocSeqPlayer(NNSSndHandle *handle, int playerNo, int prio);
void NNSi_SndPlayerFreeSeqPlayer(NNSSndSeqPlayer *player);
void NNSi_SndPlayerStartSeq(NNSSndSeqPlayer *player, const void *seqBase, u32 seqOffset, void *bank);
void NNSi_SndPlayerStopSeq(NNSSndSeqPlayer *player, int fadeFrame);
void NNSi_SndPlayerPause(NNSSndSeqPlayer *player, BOOL flag);
NNSSndHeapHandle NNSi_SndPlayerAllocHeap(int playerNo, NNSSndSeqPlayer *player);
void NNS_SndPlayerStopSeq(NNSSndHandle *handle, int fadeFrame);
void NNS_SndPlayerStopSeqBySeqNo(int seqNo, int fadeFrame);
void NNS_SndPlayerStopSeqAll(int fadeFrame);
void NNS_SndPlayerPause(NNSSndHandle *handle, BOOL flag);
void NNS_SndPlayerSetVolume(NNSSndHandle *handle, int volume);
void NNS_SndPlayerSetInitialVolume(NNSSndHandle *handle, int volume);
void NNS_SndPlayerMoveVolume(NNSSndHandle *handle, int targetVolume, int frames);
void NNS_SndPlayerSetChannelPriority(NNSSndHandle *handle, int prio);
void NNS_SndPlayerSetTrackPitch(NNSSndHandle *handle, u32 trackBitMask, int pitch);
void NNS_SndPlayerSetTrackPan(NNSSndHandle *handle, u32 trackBitMask, int pan);
void NNS_SndPlayerSetTrackAllocatableChannel(NNSSndHandle *handle, u32 trackBitMask, u32 chBitFlag);
void NNS_SndPlayerSetTempoRatio(NNSSndHandle *handle, int ratio);
void NNS_SndPlayerSetSeqNo(NNSSndHandle *handle, int seqNo);
void NNS_SndPlayerSetSeqArcNo(NNSSndHandle *handle, int seqArcNo, int index);
int NNS_SndPlayerGetSeqNo(NNSSndHandle *handle);
BOOL NNS_SndPlayerReadVariable(NNSSndHandle *handle, int varNo, s16 *var);

// ---- streams (snd_stream.c)

typedef void (*SndStrmCallback)(BOOL isAlarm, int numChannels, void **buffers, u32 blockSize, int format, void *arg);

typedef struct SndStrm {
    NNSFndLink link;
    PmSleepCallback preSleep;
    PmSleepCallback postSleep;
    int format;
    s32 isActive : 1;  // set up
    s32 isPlaying : 1; // started
    s32 unused : 30;
    u32 bufSize; // per channel
    int numBlocks;
    SndStrmCallback callback;
    void *arg;
    int curBlock;
    int volume;
    int alarmNo;
    u32 chBitFlag;
    int numChannels;
    u8 chNo[SND_CHANNEL_NUM];
} SndStrm;

typedef struct SndStrmChannel {
    void *buffer;
    int volume;
} SndStrmChannel;

extern BOOL gSndStrmListInitialized;
extern NNSFndList gSndStrmList;
extern void *gSndStrmCallbackBuffers[SND_CHANNEL_NUM];
extern SndStrmChannel gSndStrmChannels[SND_CHANNEL_NUM];

void NNS_SndStrmInit(SndStrm *strm);
BOOL NNS_SndStrmAllocChannel(SndStrm *strm, int numChannels, const u8 *chNo);
void NNS_SndStrmFreeChannel(SndStrm *strm);
BOOL NNS_SndStrmSetup(SndStrm *strm, int format, void *buffer, u32 bufSize, u32 timer, u32 numBlocks, SndStrmCallback callback, void *arg);
void NNS_SndStrmStart(SndStrm *strm);
void NNS_SndStrmStop(SndStrm *strm);
void NNS_SndStrmSetVolume(SndStrm *strm, int volume);
void ForceStopStrm(SndStrm *strm);
void ShutdownStrm(SndStrm *strm);
void AlarmCallback(void *arg);
void StrmCallback(SndStrm *strm, BOOL isAlarm);
void BeginSleep__Strm(void *arg);
void EndSleep__Strm(void *arg);

// ---- capture effects (snd_capture.c)

typedef struct SndCaptureState {
    BOOL isActive;
    int type; // 0: reverb
    u32 unk_08;
    void *bufferL;
    void *bufferR;
    u32 bufSize;
    u32 unk_18;
    u32 pos;
    u32 lockedChBitFlag;
    u32 chBitFlag;
    u32 capBitFlag;
    int alarmNo; // -1: none
    u8 unk_30[0xC];
    SndFader fader;
    BOOL isStopping;
    int volume;
    u8 unk_54[0x5B4 - 0x54];
} SndCaptureState;

typedef struct SndCaptureWork {
    u32 unk_00;
    u32 unk_04;
    OSMessageQueue msgQueue;
    OSMessage msgs[8];
    SndCaptureState state;
} SndCaptureWork;

extern SndCaptureWork gSndCaptureWork;
extern OSMessageQueue gSndCaptureMsgQueue; // gSndCaptureWork.msgQueue
extern SndCaptureState gSndCaptureState;   // gSndCaptureWork.state

void NNSi_SndCaptureInit(void);
void NNSi_SndCaptureMain(void);
void NNSi_SndCaptureStop(void);
void NNSi_SndCaptureBeginSleep(void);
void NNSi_SndCaptureEndSleep(void);
void NNS_SndCaptureStopReverb(int frames);
BOOL NNS_SndCaptureIsActive(void);
int NNS_SndCaptureGetCaptureType(void);

// ---- sound archive streams (snd_arc_strm.c)

void NNSi_SndArcStrmMain(void);

#endif // POKEHEARTGOLD_NNSYS_SND_INTERNAL_H
