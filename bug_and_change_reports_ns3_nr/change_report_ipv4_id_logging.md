# Change Report: IPv4 ID propagation in PDCP/RLC/MAC logs

## Summary
- Added an IPv4 Identification packet tag at the IPv4 layer and propagated it through NR PDCP/RLC and MAC-TB delay traces to enable per-packet correlation across logs.
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
- `pkt_id` is set from the IPv4 header’s Identification field; when not available (e.g., non-IP/control traffic), it is logged as `0`.
- All code changes are marked with `// codex added` comments.
