/* -*-  Mode: C++; c-file-style: "gnu"; indent-tabs-mode:nil; -*- */
#ifndef NR_TRACE_STREAMS_H
#define NR_TRACE_STREAMS_H

namespace ns3 {

#define NR_TRACE_STREAM_FIELDS(X)            \
    X(mobStream)                             \
    X(delayStream)                           \
    X(rttStream)                             \
    X(fragmentRxStream)                      \
    X(burstRxStream)                         \
    X(ueGroupsStream)                        \
    X(simInfoStream)                         \
    X(dlRxTbTraceStream)                     \
    X(ulRxTbTraceStream)                     \
    X(dlRxTbComponentTraceStream)            \
    X(ulRxTbComponentTraceStream)            \
    X(dlMacTbDelayStream)                    \
    X(ulMacTbDelayStream)                    \
    X(dlDataSinrStream)                      \
    X(dlCtrlSinrStream)                      \
    X(dlPdcpRxStream)                        \
    X(ulPdcpRxStream)                        \
    X(dlRlcRxStream)                         \
    X(ulRlcRxStream)                         \
    X(dlPdcpTxStream)                        \
    X(ulPdcpTxStream)                        \
    X(dlRlcTxStream)                         \
    X(ulRlcTxStream)                         \
    X(dlRlcRxComponentStream)                \
    X(ulRlcRxComponentStream)                \
    X(dlRlcTxComponentStream)                \
    X(ulRlcTxComponentStream)                \
    X(rlcHolDelayStream)                     \
    X(rlcTxQueueSojournStream)               \
    X(rlcHolGrantWaitStream)                 \
    X(loadTraceStream)                       \
    X(rsrpRsrqStream)                        \
    X(gnbBsrStream)                          \
    X(ueMacCtrlTxStream)                     \
    X(uePhyCtrlTxStream)                     \
    X(ueMacStateStream)                      \
    X(ueMacRaTimeoutStream)                  \
    X(dlMacStatsStream)                      \
    X(ulMacStatsStream)                      \
    X(srsSinrStream)

struct TraceStreams
{
#define NR_TRACE_STREAM_FIELD(name) Ptr<OutputStreamWrapper> name;
    NR_TRACE_STREAM_FIELDS(NR_TRACE_STREAM_FIELD)
#undef NR_TRACE_STREAM_FIELD
};

} // namespace ns3

#endif // NR_TRACE_STREAMS_H
