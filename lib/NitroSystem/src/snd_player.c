#include <nitro.h>
#include <nnsys/snd_internal.h>
#include <stddef.h>

#define SND_DECIBEL_SILENT (-723)

void InitPlayer(NNSSndSeqPlayer *player);
void InsertPlayerList(SndPlayerInfo *info, NNSSndSeqPlayer *player);
void InsertPrioList(NNSSndSeqPlayer *player);
void ForceStopSeq(NNSSndSeqPlayer *player);
NNSSndSeqPlayer *AllocSeqPlayer(int prio);
void ShutdownPlayer(NNSSndSeqPlayer *player);
void PlayerHeapDisposeCallback(void *mem, u32 size, u32 data1, u32 data2);
void SetPlayerPriority(NNSSndSeqPlayer *player, int prio);

void NNS_SndPlayerSetPlayerVolume(int playerNo, u8 volume) {
    gSndPlayerInfoVolume[playerNo].value = volume;
}

void NNS_SndPlayerSetPlayableSeqCount(int playerNo, int seqCount) {
    gSndPlayerInfoPlayableSeqCount[playerNo].value = (u16)seqCount;
}

void NNS_SndPlayerSetAllocatableChannel(int playerNo, u32 chBitFlag) {
    gSndPlayerInfoAllocChBitFlag[playerNo].value = chBitFlag;
}

#pragma force_active on

// carves a heap for the player's sequence data out of `heap`
BOOL NNS_SndPlayerCreateHeap(int playerNo, NNSSndHeapHandle heap, u32 size) {
    SndPlayerHeap *playerHeap = NNS_SndHeapAlloc(heap, size + sizeof(SndPlayerHeap), PlayerHeapDisposeCallback, 0, 0);
    NNSSndHeapHandle subHeap;
    if (playerHeap == NULL) {
        return FALSE;
    }
    playerHeap->player = NULL;
    playerHeap->playerNo = playerNo;
    playerHeap->heap = NULL;
    subHeap = NNS_SndHeapCreate(playerHeap->buffer, size);
    if (subHeap == NULL) {
        return FALSE;
    }
    playerHeap->heap = subHeap;
    NNS_FndAppendListObject(&gSndPlayerInfo[playerNo].heapList, playerHeap);
    return TRUE;
}

#pragma force_active off

void NNS_SndPlayerStopSeq(NNSSndHandle *handle, int fadeFrame) {
    NNSi_SndPlayerStopSeq(handle->player, fadeFrame);
}

void NNS_SndPlayerStopSeqByPlayerNo(int playerNo, int fadeFrame) {
    int i;
    NNSSndSeqPlayer *player = gSndSeqPlayers;
    SndPlayerInfo *info = &gSndPlayerInfo[playerNo];
    for (i = 0; i < SND_SEQ_PLAYER_NUM; i++, player++) {
        if (player->status != SND_SEQ_PLAYER_STATUS_FREE && player->playerInfo == info) {
            NNSi_SndPlayerStopSeq(player, fadeFrame);
        }
    }
}

void NNS_SndPlayerStopSeqBySeqNo(int seqNo, int fadeFrame) {
    int i;
    NNSSndSeqPlayer *player = gSndSeqPlayers;
    for (i = 0; i < SND_SEQ_PLAYER_NUM; i++, player++) {
        if (player->status != SND_SEQ_PLAYER_STATUS_FREE && player->seqType == SND_SEQ_TYPE_SEQ && player->seqNo == seqNo) {
            NNSi_SndPlayerStopSeq(player, fadeFrame);
        }
    }
}

void NNS_SndPlayerStopSeqAll(int fadeFrame) {
    int i;
    NNSSndSeqPlayer *player = gSndSeqPlayers;
    for (i = 0; i < SND_SEQ_PLAYER_NUM; i++, player++) {
        if (player->status != SND_SEQ_PLAYER_STATUS_FREE) {
            NNSi_SndPlayerStopSeq(player, fadeFrame);
        }
    }
}

void NNS_SndPlayerPause(NNSSndHandle *handle, BOOL flag) {
    NNSi_SndPlayerPause(handle->player, flag);
}

#pragma force_active on

void NNS_SndPlayerPauseByPlayerNo(int playerNo, BOOL flag) {
    NNSSndSeqPlayer *player = NNS_FndGetNextListObject(&gSndPlayerInfo[playerNo].playerList, NULL);
    while (player != NULL) {
        NNSSndSeqPlayer *next = NNS_FndGetNextListObject(&gSndPlayerInfo[playerNo].playerList, player);
        NNSi_SndPlayerPause(player, flag);
        player = next;
    }
}

#pragma force_active off

void NNS_SndHandleInit(NNSSndHandle *handle) {
    handle->player = NULL;
}

void NNS_SndHandleReleaseSeq(NNSSndHandle *handle) {
    if (SND_HANDLE_PLAYER(handle) != NULL) {
        SND_HANDLE_PLAYER(handle)->handle = NULL;
        SND_HANDLE_PLAYER(handle) = NULL;
    }
}

int NNS_SndPlayerCountPlayingSeqByPlayerNo(int playerNo) {
    return gSndPlayerInfoNumPlaying[playerNo].value;
}

void NNS_SndPlayerSetVolume(NNSSndHandle *handle, int volume) {
    if (SND_HANDLE_PLAYER(handle) != NULL) {
        SND_HANDLE_PLAYER(handle)->extVolume = volume;
    }
}

void NNS_SndPlayerSetInitialVolume(NNSSndHandle *handle, int volume) {
    if (SND_HANDLE_PLAYER(handle) != NULL) {
        SND_HANDLE_PLAYER(handle)->initVolume = volume;
    }
}

#pragma force_active on

void NNS_SndPlayerMoveVolume(NNSSndHandle *handle, int targetVolume, int frames) {
    NNSSndSeqPlayer *player;
    if (SND_HANDLE_PLAYER(handle) != NULL && (player = SND_HANDLE_PLAYER(handle))->status != SND_SEQ_PLAYER_STATUS_FADEOUT) {
        NNSi_SndFaderSet(&player->fader, targetVolume << 8, frames);
    }
}

#pragma force_active off

void NNS_SndPlayerSetChannelPriority(NNSSndHandle *handle, int prio) {
    if (SND_HANDLE_PLAYER(handle) != NULL) {
        SND_SetPlayerChannelPriority(SND_HANDLE_PLAYER(handle)->playerNo, prio);
    }
}

void NNS_SndPlayerSetTrackPitch(NNSSndHandle *handle, u32 trackBitMask, int pitch) {
    if (SND_HANDLE_PLAYER(handle) != NULL) {
        SND_SetTrackPitch(SND_HANDLE_PLAYER(handle)->playerNo, trackBitMask, pitch);
    }
}

void NNS_SndPlayerSetTrackPan(NNSSndHandle *handle, u32 trackBitMask, int pan) {
    if (SND_HANDLE_PLAYER(handle) == NULL) {
        return;
    }
    SND_SetTrackPan(SND_HANDLE_PLAYER(handle)->playerNo, trackBitMask, pan);
}

void NNS_SndPlayerSetTrackAllocatableChannel(NNSSndHandle *handle, u32 trackBitMask, u32 chBitFlag) {
    if (SND_HANDLE_PLAYER(handle) == NULL) {
        return;
    }
    SND_SetTrackAllocatableChannel(SND_HANDLE_PLAYER(handle)->playerNo, trackBitMask, chBitFlag);
}

void NNS_SndPlayerSetTempoRatio(NNSSndHandle *handle, int ratio) {
    if (SND_HANDLE_PLAYER(handle) == NULL) {
        return;
    }
    SND_SetPlayerTempoRatio(SND_HANDLE_PLAYER(handle)->playerNo, ratio);
}

void NNS_SndPlayerSetSeqNo(NNSSndHandle *handle, int seqNo) {
    if (SND_HANDLE_PLAYER(handle) == NULL) {
        return;
    }
    SND_HANDLE_PLAYER(handle)->seqType = SND_SEQ_TYPE_SEQ;
    SND_HANDLE_PLAYER(handle)->seqNo = seqNo;
}

void NNS_SndPlayerSetSeqArcNo(NNSSndHandle *handle, int seqArcNo, int index) {
    if (SND_HANDLE_PLAYER(handle) == NULL) {
        return;
    }
    SND_HANDLE_PLAYER(handle)->seqType = SND_SEQ_TYPE_SEQARC;
    SND_HANDLE_PLAYER(handle)->seqNo = seqArcNo;
    SND_HANDLE_PLAYER(handle)->seqArcIdx = index;
}

int NNS_SndPlayerGetSeqNo(NNSSndHandle *handle) {
    NNSSndSeqPlayer *player;
    if (SND_HANDLE_PLAYER(handle) == NULL) {
        return -1;
    }
    player = SND_HANDLE_PLAYER(handle);
    if (player->seqType != SND_SEQ_TYPE_SEQ) {
        return -1;
    }
    return player->seqNo;
}

#pragma force_active on

BOOL NNS_SndPlayerReadVariable(NNSSndHandle *handle, int varNo, s16 *var) {
    NNSSndSeqPlayer *player;
    if (SND_HANDLE_PLAYER(handle) == NULL) {
        return FALSE;
    }
    player = SND_HANDLE_PLAYER(handle);
    if (!player->isStarted) {
        *var = -1;
        return TRUE;
    }
    *var = SND_GetPlayerLocalVariable(player->playerNo, varNo);
    return TRUE;
}

#pragma force_active off

BOOL NNS_SndPlayerReadDriverTrackInfo(NNSSndHandle *handle, int trackNo, SNDTrackInfo *info) {
    if (SND_HANDLE_PLAYER(handle) == NULL) {
        return FALSE;
    }
    return NNSi_SndReadDriverTrackInfo(SND_HANDLE_PLAYER(handle)->playerNo, trackNo, info);
}

#pragma force_active on

void NNSi_SndPlayerInit(void) {
    int i;
    NNSSndSeqPlayer *player;
    SndPlayerInfo *info;

    NNS_FndInitList(&gSndSeqPlayerPrioList, offsetof(NNSSndSeqPlayer, prioLink));
    NNS_FndInitList(&gSndFreeSeqPlayerList, offsetof(NNSSndSeqPlayer, prioLink));
    for (i = 0, player = gSndSeqPlayers; i < SND_SEQ_PLAYER_NUM; i++, player++) {
        player->status = SND_SEQ_PLAYER_STATUS_FREE;
        player->playerNo = i;
        NNS_FndAppendListObject(&gSndFreeSeqPlayerList, player);
    }
    for (i = 0, info = gSndPlayerInfo; i < SND_PLAYER_NUM; i++, info++) {
        NNS_FndInitList(&info->playerList, offsetof(NNSSndSeqPlayer, playerLink));
        NNS_FndInitList(&info->heapList, offsetof(SndPlayerHeap, link));
        info->volume = 127;
        info->playableSeqCount = 1;
        info->allocChBitFlag = 0;
    }
}

#pragma force_active off

static inline int CombineDecibels(int player, int init, int ext, int fade) {
    return fade + (player + (init + ext));
}

#pragma force_active on

// starts prepared sequences, frees finished players and updates the player volumes
void NNSi_SndPlayerMain(void) {
    u32 playerStatus = SND_GetPlayerStatus();
    NNSSndSeqPlayer *player = NNS_FndGetNextListObject(&gSndSeqPlayerPrioList, NULL);
    while (player != NULL) {
        NNSSndSeqPlayer *next = NNS_FndGetNextListObject(&gSndSeqPlayerPrioList, player);
        int volume;
        if (!player->isStarted) {
            if (SND_IsFinishedCommandTag(player->prepareTag)) {
                player->isStarted = TRUE;
            }
        }
        if (player->isStarted && !(playerStatus & (1U << player->playerNo))) {
            ShutdownPlayer(player);
        } else {
            s32 extDecibel, initDecibel, playerDecibel;
            NNSi_SndFaderUpdate(&player->fader);
            extDecibel = SNDi_DecibelTable[player->extVolume];
            initDecibel = SNDi_DecibelTable[player->initVolume];
            playerDecibel = SNDi_DecibelTable[player->playerInfo->volume];
            volume = CombineDecibels(playerDecibel, initDecibel, extDecibel, SNDi_DecibelTable[NNSi_SndFaderGet(&player->fader) >> 8]);
            if (volume < -32768) {
                volume = -32768;
            } else if (volume > 32767) {
                volume = 32767;
            }
            if (volume != player->volume) {
                SND_SetPlayerVolume(player->playerNo, volume);
                player->volume = volume;
            }
            if (player->status == SND_SEQ_PLAYER_STATUS_FADEOUT && NNSi_SndFaderIsFinished(&player->fader)) {
                ForceStopSeq(player);
            }
            if (player->isPrepared) {
                SND_StartPreparedSeq(player->playerNo);
                player->isPrepared = FALSE;
            }
        }
        player = next;
    }
}

// takes a free sequence player for `handle`; when the player already plays its maximum number of
// sequences, the lowest priority one is stopped if `prio` is not lower
NNSSndSeqPlayer *NNSi_SndPlayerAllocSeqPlayer(NNSSndHandle *handle, int playerNo, int prio) {
    SndPlayerInfo *info = &gSndPlayerInfo[playerNo];
    NNSSndSeqPlayer *player = handle->player;
    if (player != NULL) {
        NNS_SndHandleReleaseSeq(handle);
    }
    if (info->playerList.numObjects >= info->playableSeqCount) {
        player = NNS_FndGetNextListObject(&info->playerList, NULL);
        if (player == NULL) {
            return NULL;
        }
        if (prio < player->priority) {
            return NULL;
        }
        ForceStopSeq(player);
    }
    player = AllocSeqPlayer(prio);
    if (player == NULL) {
        return NULL;
    }
    InsertPlayerList(info, player);
    player->handle = handle;
    handle->player = player;
    return player;
}

#pragma force_active off

void NNSi_SndPlayerFreeSeqPlayer(NNSSndSeqPlayer *player) {
    ShutdownPlayer(player);
}

#pragma force_active on

void NNSi_SndPlayerStartSeq(NNSSndSeqPlayer *player, const void *seqBase, u32 seqOffset, void *bank) {
    SndPlayerInfo *info = player->playerInfo;
    SND_PrepareSeq(player->playerNo, seqBase, seqOffset, bank);
    if (info->allocChBitFlag) {
        SND_SetTrackAllocatableChannel(player->playerNo, 0xFFFF, info->allocChBitFlag);
    }
    InitPlayer(player);
    player->prepareTag = SND_GetCurrentCommandTag();
    player->isPrepared = TRUE;
    player->status = SND_SEQ_PLAYER_STATUS_PLAY;
}

void NNSi_SndPlayerStopSeq(NNSSndSeqPlayer *player, int fadeFrame) {
    if (player == NULL || player->status == SND_SEQ_PLAYER_STATUS_FREE) {
        return;
    }
    if (fadeFrame == 0) {
        ForceStopSeq(player);
        return;
    }
    NNSi_SndFaderSet(&player->fader, 0, fadeFrame);
    SetPlayerPriority(player, 0);
    player->status = SND_SEQ_PLAYER_STATUS_FADEOUT;
}

#pragma force_active off

void NNSi_SndPlayerPause(NNSSndSeqPlayer *player, BOOL flag) {
    if (player == NULL || flag == player->isPaused) {
        return;
    }
    SND_PauseSeq(player->playerNo, flag);
    player->isPaused = flag;
}

#pragma force_active on

// hands a free heap of the player to `player`, cleared
NNSSndHeapHandle NNSi_SndPlayerAllocHeap(int playerNo, NNSSndSeqPlayer *player) {
    NNSFndList *heapList = &gSndPlayerInfo[playerNo].heapList;
    SndPlayerHeap *playerHeap = NNS_FndGetNextListObject(heapList, NULL);
    if (playerHeap == NULL) {
        return NULL;
    }
    NNS_FndRemoveListObject(heapList, playerHeap);
    playerHeap->player = player;
    player->heap = playerHeap;
    NNS_SndHeapClear(playerHeap->heap);
    return playerHeap->heap;
}

void InitPlayer(NNSSndSeqPlayer *player) {
    player->isPaused = FALSE;
    player->isStarted = FALSE;
    player->isPrepared = FALSE;
    player->seqType = SND_SEQ_TYPE_NONE;
    player->volume = 0;
    player->initVolume = 127;
    player->extVolume = 127;
    NNSi_SndFaderInit(&player->fader);
    NNSi_SndFaderSet(&player->fader, 127 << 8, 1);
}

// sorted by priority, lowest first
void InsertPlayerList(SndPlayerInfo *info, NNSSndSeqPlayer *player) {
    NNSSndSeqPlayer *next = NNS_FndGetNextListObject(&info->playerList, NULL);
    while (next != NULL) {
        if (player->priority < next->priority) {
            break;
        }
        next = NNS_FndGetNextListObject(&info->playerList, next);
    }
    NNS_FndInsertListObject(&info->playerList, next, player);
    player->playerInfo = info;
}

void InsertPrioList(NNSSndSeqPlayer *player) {
    NNSSndSeqPlayer *next = NNS_FndGetNextListObject(&gSndSeqPlayerPrioList, NULL);
    while (next != NULL) {
        if (player->priority < next->priority) {
            break;
        }
        next = NNS_FndGetNextListObject(&gSndSeqPlayerPrioList, next);
    }
    NNS_FndInsertListObject(&gSndSeqPlayerPrioList, next, player);
}

void ForceStopSeq(NNSSndSeqPlayer *player) {
    if (player->status == SND_SEQ_PLAYER_STATUS_FADEOUT) {
        SND_SetPlayerVolume(player->playerNo, SND_DECIBEL_SILENT);
    }
    SND_StopSeq(player->playerNo);
    ShutdownPlayer(player);
}

// takes a free sequence player, or the lowest priority one if `prio` is not lower
NNSSndSeqPlayer *AllocSeqPlayer(int prio) {
    NNSSndSeqPlayer *player = NNS_FndGetNextListObject(&gSndFreeSeqPlayerList, NULL);
    if (player == NULL) {
        player = NNS_FndGetNextListObject(&gSndSeqPlayerPrioList, NULL);
        if (prio < player->priority) {
            return NULL;
        }
        ForceStopSeq(player);
    }
    NNS_FndRemoveListObject(&gSndFreeSeqPlayerList, player);
    player->priority = prio;
    InsertPrioList(player);
    return player;
}

void ShutdownPlayer(NNSSndSeqPlayer *player) {
    SndPlayerInfo *info;
    if (player->handle != NULL) {
        player->handle->player = NULL;
        player->handle = NULL;
    }
    info = player->playerInfo;
    NNS_FndRemoveListObject(&info->playerList, player);
    player->playerInfo = NULL;
    if (player->heap != NULL) {
        NNS_FndAppendListObject(&info->heapList, player->heap);
        player->heap->player = NULL;
        player->heap = NULL;
    }
    NNS_FndRemoveListObject(&gSndSeqPlayerPrioList, player);
    NNS_FndAppendListObject(&gSndFreeSeqPlayerList, player);
    player->status = SND_SEQ_PLAYER_STATUS_FREE;
}

void PlayerHeapDisposeCallback(void *mem, u32 size, u32 data1, u32 data2) {
    SndPlayerHeap *playerHeap = mem;
    if (playerHeap->heap == NULL) {
        return;
    }
    NNS_SndHeapDestroy(playerHeap->heap);
    if (playerHeap->player != NULL) {
        playerHeap->player->heap = NULL;
    } else {
        NNS_FndRemoveListObject(&gSndPlayerInfo[playerHeap->playerNo].heapList, playerHeap);
    }
}

void SetPlayerPriority(NNSSndSeqPlayer *player, int prio) {
    SndPlayerInfo *info = player->playerInfo;
    if (info != NULL) {
        NNS_FndRemoveListObject(&info->playerList, player);
        player->playerInfo = NULL;
    }
    NNS_FndRemoveListObject(&gSndSeqPlayerPrioList, player);
    player->priority = prio;
    if (info != NULL) {
        InsertPlayerList(info, player);
    }
    InsertPrioList(player);
}
