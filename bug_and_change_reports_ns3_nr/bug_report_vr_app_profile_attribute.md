# VR App Profile Attribute Bug

## Environment
- ns-3 dev tree with `contrib/vr-app`
- Example observed through: `contrib/nr/examples/5G-LENA-digital-twin-script/cellular-network-user`
- Traffic mode: `--vrTrafficType=synthetic`

## Symptom
Changing `--vrAppProfile` in the cellular-network scenario records different requested profile names
in `run_cmd.txt`, `sim_info.txt`, and stdout, but the synthetic VR burst outputs remain identical.

Observed identical raw trace hashes across profile-variation runs:
- `vrBurst_trace.txt`
- `vrFragment_trace.txt`
- downstream parsed uplink CSVs

## Root Cause
`VrBurstGenerator` registered the `VrAppName` attribute with a direct member accessor to `m_appName`.
When the attribute was set through ns-3's attribute system or `ObjectFactory`, it updated `m_appName`
without calling `SetVrAppName()`.

`SetVrAppName()` is responsible for calling `SetupModel()`, which rebuilds the logistic random
variables with the selected application's profile parameters. Bypassing the setter left the model
configured with the default profile.

## Fix
Register `VrAppName` with the setter/getter accessor:

```cpp
MakeEnumAccessor<VrAppName>(&VrBurstGenerator::SetVrAppName,
                            &VrBurstGenerator::GetVrAppName)
```

This keeps the public attribute and cellular-network CLI unchanged while ensuring any ns-3
attribute-based configuration path rebuilds the VR traffic model for the selected profile.
