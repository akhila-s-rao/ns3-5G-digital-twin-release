# BeamId Vector Uninitialized -> SIGSEGV (NR HARQ)

## Environment
- ns-3 dev tree with NR contrib
- Example: `contrib/nr/examples/5G-LENA-digital-twin-script/cellular-network-user`
- Scenario: `--digitalTwinScenario=expeca` (10 UEs, 5 VR UEs)

## Symptom
Simulation crashes with SIGSEGV during DL HARQ scheduling.

### Runtime log excerpt
```
Command 'build/contrib/nr/examples/ns3.46-cellular-network-user-optimized ... --randomSeed=9' died with <Signals.SIGSEGV: 11>.
```

### gdb backtrace excerpt
```
#0  __gnu_cxx::__normal_iterator<...>::__normal_iterator(...)
#1  std::vector<...>::begin (this=0x18)
#2  ns3::NrMacSchedulerHarqRr::ScheduleDlHarq(...)
    at /home/ubuntu/ns-3-dev/contrib/nr/model/nr-mac-scheduler-harq-rr.cc:170
#3  ns3::NrMacSchedulerNs3::ScheduleDlHarq(...)
    at /home/ubuntu/ns-3-dev/contrib/nr/model/nr-mac-scheduler-ns3.cc:496
```

## Root cause
In `NrMacSchedulerHarqRr::GetBeamOrderRR`, the return vector was pre-sized to
`activeHarqMap.size()` but only populated when the beam at the front of the
round-robin queue was active. Default/uninitialized `BeamId` values were left
in the vector, and the caller then did:

```
const auto& beam = *activeDlHarq.find(beamId);
```

When `beamId` is not present, `find()` returns `end()`, which is dereferenced,
leading to the SIGSEGV.

## Suggested fix
Build the return vector by pushing only active beams, instead of pre-sizing
and partially filling it. This ensures all `beamId`s returned are valid keys in
`activeHarqMap`.

