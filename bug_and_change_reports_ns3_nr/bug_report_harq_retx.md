# HARQ ReTx Scheduling Bugs (NR)

## Environment
- ns-3 dev tree with NR contrib
- Example: `contrib/nr/examples/5G-LENA-digital-twin-script/cellular-network-user`
- Scenario: `--digitalTwinScenario=expeca` (10 UEs, 5 VR UEs)
- Repro seed: `--randomSeed=6` (also seen with other seeds)

## Reproduction
Run with HARQ retransmissions enabled (default):

```bash
NS_LOG="NrMacSchedulerHarqRr=level_info|prefix_time|prefix_func|prefix_node" \
./ns3 run --no-build "cellular-network-user --digitalTwinScenario=expeca --numUes=10 \
--numUesWithVrApp=5 --vrTrafficType=synthetic --vrFrameRate=30 --vrTargetDataRateMbps=10 \
--vrAppProfile=VirusPopper --appGenerationTime=1000 --progressInterval=1s \
--vrBearerQci=80 --controlBearerQci=80 --createRemMap=false --randomSeed=6"
```

## Issue 1: SIGSEGV in HARQ DL scheduling (pre-fix)
### Symptom
Segmentation fault in `NrMacSchedulerHarqRr::ScheduleDlHarq` when dereferencing
`activeDlHarq.find(beamId)` with an invalid `beamId`.

### Backtrace (excerpt)
```
#1  std::vector<...>::begin (this=0x18)
#2  ns3::NrMacSchedulerHarqRr::ScheduleDlHarq (...)
    at contrib/nr/model/nr-mac-scheduler-harq-rr.cc:170
```

### Root cause
`GetBeamOrderRR` pre-sized the return vector but only assigned some entries,
leaving default/uninitialized `BeamId` values. These could be missing in
`activeDlHarq`, so `find()` returned `end()` and was dereferenced.

### Suggested fix
Build the return vector by `push_back` only for active beams, rather than
pre-sizing and partially filling it.

## Issue 2: HARQ symbol over-allocation -> NS_ASSERT abort
### Symptom
```
NS_ASSERT failed, cond="dlSymAvail >= usedHarq",
msg="DlSymAvail (13) < usedHarq (20)",
file=contrib/nr/model/nr-mac-scheduler-ns3.cc:2385
```

### NS_LOG excerpt showing underflow
```
... ScheduleDlHarq(): Evaluating space to retransmit HARQ PID=15 for UE=4 ... SYM avail=13
... HARQ DL alloc rnti=4 harqId=15 symStart=1 numSym=7 currStartSym=1 symAvail=6
... HARQ DL symbolsUsedForBeam=7 symAvail(before)=6 currStartingSymbol=1
... HARQ DL symAvail(after)=255 currStartingSymbol=8
... ScheduleDlHarq(): Evaluating space to retransmit HARQ PID=2 for UE=5 ... SYM avail=255
... HARQ DL usedSymbols=20 startSym=1 symAvailEnd=229 newDciCount=2
```

### Root cause
In `NrMacSchedulerHarqRr::ScheduleDlHarq`, `symAvail` is reduced twice:
1) Per-HARQ in the non-reshaping path:
   `symAvailBackup -= harqProcess.m_dciElement->m_numSym;`
2) Per-beam after scheduling:
   `symAvail -= symbolsUsedForBeam;`

For OFDMA, multiple HARQ DCIs within the same beam share the same symbol range,
so only the per-beam decrement is valid. The double-decrement underflows
`uint8_t` to 255, leading to over-allocation and the assert.

### Suggested fix
Remove the per-HARQ decrement in the non-reshaping path, and keep the
per-beam `symAvail -= symbolsUsedForBeam` update. This preserves the intended
OFDMA time accounting and prevents underflow.

