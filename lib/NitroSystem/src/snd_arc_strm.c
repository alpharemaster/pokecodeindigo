#include <nitro.h>
#include <nnsys/snd_arc_strm_internal.h>

#pragma force_active off

static inline int AddDecibels(int fade, int init) {
    return fade + init;
}

#pragma force_active on

// starts prepared streams once ready and updates their volume and fade-out
void NNSi_SndArcStrmMain(void) {
    int i;
    for (i = 0; i < SND_ARC_STRM_PLAYER_NUM; i++) {
        SndArcStrmPlayer *player = &gSndArcStrmPlayers[i];
        if (player->isActive) {
            if (!player->isValid) {
                ForceStopStrm__SndArc(player);
            } else {
                if (player->isPrepared && player->isReady) {
                    NNS_SndStrmStart(&player->strm);
                    player->isStarted = TRUE;
                    player->isPrepared = FALSE;
                }
                if (player->isStarted) {
                    int volume;
                    NNSi_SndFaderUpdate(&player->fader);
                    volume = SNDi_DecibelTable[player->initVolume];
                    {
                        int fadeVolume = NNSi_SndFaderGet(&player->fader) >> 8;
                        int extVolume = player->extVolume;
                        volume = SNDi_DecibelTable[extVolume] + AddDecibels(SNDi_DecibelTable[fadeVolume], volume);
                    }
                    if (volume != player->volume) {
                        NNS_SndStrmSetVolume(&player->strm, volume);
                        player->volume = volume;
                    }
                    if (player->isFadeOut && NNSi_SndFaderIsFinished(&player->fader)) {
                        ForceStopStrm__SndArc(player);
                    }
                }
            }
        }
    }
}

void FreePlayer(SndArcStrmPlayer *player) {
    if (player->handle) {
        player->handle->player = NULL;
        player->handle = NULL;
    }
    player->isActive = FALSE;
    player->isPrepared = FALSE;
    player->isStarted = FALSE;
}

void ForceStopStrm__SndArc(SndArcStrmPlayer *player) {
    OS_LockMutex(&gSndArcStrmMutex);
    if (_021E0950.threadWork) {
        OS_LockMutex(&_021E0950.threadWork->mutex);
    }
    if (player->isStarted) {
        NNS_SndStrmStop(&player->strm);
    }
    if (player->isActive) {
        player->stopFunc(player);
    }
    ShutdownPlayer__SndArc(player);
    OS_UnlockMutex(&gSndArcStrmMutex);
    if (_021E0950.threadWork) {
        OS_UnlockMutex(&_021E0950.threadWork->mutex);
    }
}

void ShutdownPlayer__SndArc(SndArcStrmPlayer *player) {
    if (!player->isActive) {
        return;
    }
    FreeChannel(player);
    player->disposeFunc(player);
    RemoveCommandByPlayer(&gSndArcStrmCommandList, player);
    if (_021E0950.threadWork) {
        RemoveCommandByPlayer(&_021E0950.threadWork->commandList, player);
    }
    FreePlayer(player);
}

#pragma force_active off

void FreeChannel(SndArcStrmPlayer *player) {
    u32 refCount = player->chRefCount;
    if (refCount == 0) {
        return;
    }
    refCount--;
    player->chRefCount = refCount;
    if (refCount == 0) {
        NNS_SndStrmFreeChannel(&player->strm);
    }
}

#pragma force_active on
#pragma push
#pragma opt_lifetimes off // needed for the match

void RemoveCommandByPlayer(NNSFndList *commandList, SndArcStrmPlayer *player) {
    OSIntrMode intrMode = OS_DisableInterrupts();
    SndArcStrmCommand *command = NNS_FndGetNextListObject(commandList, NULL), *next;
    while (command) {
        next = NNS_FndGetNextListObject(commandList, command);
        if (command->player == player) {
            NNS_FndRemoveListObject(commandList, command);
            FreeCommandBuffer(command);
        }
        command = next;
    }
    OS_RestoreInterrupts(intrMode);
}

#pragma pop
#pragma force_active off

void FreeCommandBuffer(SndArcStrmCommand *command) {
    OSIntrMode intrMode = OS_DisableInterrupts();
    NNS_FndAppendListObject(&gSndArcStrmFreeCommandList, command);
    OS_RestoreInterrupts(intrMode);
}
