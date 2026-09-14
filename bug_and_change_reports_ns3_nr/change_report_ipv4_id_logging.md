# Change Report: IPv4 tracing ID propagation in PDCP/RLC/MAC logs

## Summary
- Added a 32-bit per-node IPv4 tracing-ID ByteTag and propagated it through NR PDCP/RLC and MAC-TB delay traces to enable per-packet correlation across logs.
- Extended PDCP/RLC/MAC trace signatures and log headers in both `cellular-network` and `delay-benchmarking` scripts to include `pkt_id`.
- Updated logging documentation to reflect the new `pkt_id` column.

## Files changed
- `src/internet/model/ipv4-id-tag.h` (new)
- `src/internet/model/ipv4-id-tag.cc` (new)
- `src/internet/CMakeLists.txt`
- `src/internet/model/ipv4-l3-protocol.cc`
- `contrib/nr/model/nr-pdcp.h`
- `contrib/nr/model/nr-pdcp.cc`
- `contrib/nr/model/nr-rlc.h`
- `contrib/nr/model/nr-rlc.cc`
- `contrib/nr/model/nr-rlc-um.cc`
- `contrib/nr/model/nr-rlc-am.cc`
- `contrib/nr/model/nr-spectrum-phy.h`
- `contrib/nr/model/nr-spectrum-phy.cc`
- `contrib/nr/examples/5G-LENA-digital-twin-script/cellular-network.h`
- `contrib/nr/examples/5G-LENA-digital-twin-script/delay-benchmarking.h`
- `contrib/nr/examples/5G-LENA-digital-twin-script/logging_documentation.txt`

## Notes
- Identifiable IPv4 packets use a per-node 32-bit counter starting at `1`.
- `pkt_id = 0` is reserved for bytes without an available tracing tag, such as control/header-only components. These sentinel records must not be correlated as one packet and are excluded from delay decomposition.
- All code changes are marked with `// codex added` comments.

## Follow-up corrections

- The tracing counter originally started at zero even though zero was also the unavailable-tag
  sentinel. This made the first identifiable packet on each node collide with every unidentified
  component for the same `(rnti, lcid)`.
- The counter now starts at one, and `create_delay_decomposition_data.py` explicitly rejects
  non-positive packet IDs. Existing raw traces remain usable after filtering the sentinel rows;
  no simulation rerun is required for this correction.
