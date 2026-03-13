/* -*-  Mode: C++; c-file-style: "gnu"; indent-tabs-mode:nil; -*- */
#ifndef NR_TRACE_COMMON_H
#define NR_TRACE_COMMON_H

#include <cmath>
#include <cstdint>
#include <string>

inline bool
IsStreamReady(const Ptr<OutputStreamWrapper>& stream)
{
    return stream != nullptr && stream->GetStream() != nullptr;
}

inline double
SlotsToMicroseconds(uint32_t slots, uint8_t numerology)
{
    return static_cast<double>(slots) * (1000.0 / static_cast<double>(1u << numerology));
}

inline double
UlSendStartDeltaMicroseconds(uint32_t kDelaySlots,
                             uint8_t numerology,
                             uint8_t symStart,
                             uint32_t symbolsPerSlot)
{
    const uint32_t safeSymbolsPerSlot = (symbolsPerSlot > 0) ? symbolsPerSlot : 14;
    const double slotPeriodUs = SlotsToMicroseconds(1, numerology);
    const double symbolPeriodUs = slotPeriodUs / static_cast<double>(safeSymbolsPerSlot);
    return SlotsToMicroseconds(kDelaySlots, numerology) +
           (static_cast<double>(symStart) * symbolPeriodUs);
}

inline void
WriteHeader(Ptr<OutputStreamWrapper> stream, const std::string& header)
{
    if (!IsStreamReady(stream))
    {
        return;
    }
    *stream->GetStream() << header << std::endl;
}

inline uint16_t
ResolveCellIdFromRnti(uint16_t rnti)
{
    auto it = g_rntiToCellId.find(rnti);
    return (it != g_rntiToCellId.end()) ? it->second : 0;
}

inline uint16_t
ResolveUeIdFromContext(const std::string& context)
{
    return GetUeIdFromNodeId(GetNodeIdFromContext(context));
}

inline uint16_t
ResolveCellIdFromContext(const std::string& context)
{
    return GetCellId_from_ueId(ResolveUeIdFromContext(context));
}

inline uint64_t
ResolveImsiFromContext(const std::string& context)
{
    return GetImsi_from_ueId(ResolveUeIdFromContext(context));
}

inline void
WriteUeSinrTrace(Ptr<OutputStreamWrapper> stream,
                 uint16_t cellId,
                 uint16_t rnti,
                 double avgSinr,
                 uint16_t bwpId)
{
    if (!IsStreamReady(stream))
    {
        return;
    }

    *stream->GetStream() << Simulator::Now().GetMicroSeconds() << "\t" << cellId << "\t" << rnti
                         << "\t" << static_cast<uint32_t>(bwpId) << "\t"
                         << 10 * log10(avgSinr) << std::endl;
}

inline void
WriteRxPduTrace(Ptr<OutputStreamWrapper> stream,
                uint16_t cellId,
                uint16_t rnti,
                uint8_t lcid,
                uint32_t ipId,
                uint32_t packetSize,
                uint64_t delay)
{
    if (!IsStreamReady(stream))
    {
        return;
    }

    const uint64_t nowMicros = Simulator::Now().GetMicroSeconds();
    const uint64_t delayMicros = delay / 1000;

    *stream->GetStream() << nowMicros << "\t" << cellId << "\t" << rnti << "\t"
                         << static_cast<uint32_t>(lcid) << "\t" << ipId << "\t" << packetSize
                         << "\t" << delayMicros << std::endl;
}

inline void
WriteTxPduTrace(Ptr<OutputStreamWrapper> stream,
                uint16_t cellId,
                uint16_t rnti,
                uint8_t lcid,
                uint32_t ipId,
                uint32_t packetSize)
{
    if (!IsStreamReady(stream))
    {
        return;
    }

    const uint64_t nowMicros = Simulator::Now().GetMicroSeconds();
    *stream->GetStream() << nowMicros << "\t" << cellId << "\t" << rnti << "\t"
                         << static_cast<uint32_t>(lcid) << "\t" << ipId << "\t" << packetSize
                         << std::endl;
}

inline void
WriteRxPduComponentTrace(Ptr<OutputStreamWrapper> stream,
                         uint16_t cellId,
                         uint16_t rnti,
                         uint8_t lcid,
                         uint16_t rlcSn,
                         uint32_t rlcPduBytes,
                         uint32_t pktId,
                         uint32_t componentBytes,
                         uint64_t delayNs)
{
    if (!IsStreamReady(stream))
    {
        return;
    }

    const uint64_t nowMicros = Simulator::Now().GetMicroSeconds();
    const uint64_t delayMicros = delayNs / 1000;
    *stream->GetStream() << nowMicros << "\t" << cellId << "\t" << rnti << "\t"
                         << static_cast<uint32_t>(lcid) << "\t" << rlcSn << "\t"
                         << rlcPduBytes << "\t" << pktId << "\t" << componentBytes << "\t"
                         << delayMicros << std::endl;
}

inline void
WriteTxPduComponentTrace(Ptr<OutputStreamWrapper> stream,
                         uint16_t cellId,
                         uint16_t rnti,
                         uint8_t lcid,
                         uint16_t rlcSn,
                         uint32_t rlcPduBytes,
                         uint32_t pktId,
                         uint32_t componentBytes)
{
    if (!IsStreamReady(stream))
    {
        return;
    }

    const uint64_t nowMicros = Simulator::Now().GetMicroSeconds();
    *stream->GetStream() << nowMicros << "\t" << cellId << "\t" << rnti << "\t"
                         << static_cast<uint32_t>(lcid) << "\t" << rlcSn << "\t"
                         << rlcPduBytes << "\t" << pktId << "\t" << componentBytes
                         << std::endl;
}

inline void
WriteRxTbComponentTrace(Ptr<OutputStreamWrapper> stream,
                        const RxPacketTraceParams& params,
                        uint8_t lcid,
                        uint64_t rxPduId,
                        uint32_t rxPduBytes,
                        uint32_t pktId,
                        uint32_t componentBytes)
{
    if (!IsStreamReady(stream))
    {
        return;
    }

    *stream->GetStream() << Simulator::Now().GetMicroSeconds() << "\t" << rxPduId << "\t"
                         << params.m_frameNum << "\t"
                         << static_cast<uint32_t>(params.m_subframeNum) << "\t"
                         << static_cast<uint32_t>(params.m_slotNum) << "\t"
                         << static_cast<uint32_t>(params.m_symStart) << "\t"
                         << static_cast<uint32_t>(params.m_numSym) << "\t" << params.m_cellId
                         << "\t" << static_cast<uint32_t>(params.m_bwpId) << "\t" << params.m_rnti
                         << "\t" << static_cast<uint32_t>(lcid) << "\t" << params.m_tbSize << "\t"
                         << rxPduBytes << "\t" << static_cast<uint32_t>(params.m_mcs) << "\t"
                         << static_cast<uint32_t>(params.m_rank) << "\t"
                         << static_cast<uint32_t>(params.m_rv) << "\t"
                         << 10 * log10(params.m_sinr) << "\t"
                         << static_cast<uint32_t>(params.m_cqi) << "\t" << params.m_corrupt << "\t"
                         << params.m_tbler << "\t" << pktId << "\t" << componentBytes << std::endl;
}

inline const char*
ControlMsgTypeToString(NrControlMessage::messageType type)
{
    switch (type)
    {
        case NrControlMessage::UL_DCI:
            return "UL_DCI";
        case NrControlMessage::DL_DCI:
            return "DL_DCI";
        case NrControlMessage::DL_CQI:
            return "DL_CQI";
        case NrControlMessage::MIB:
            return "MIB";
        case NrControlMessage::SIB1:
            return "SIB1";
        case NrControlMessage::RACH_PREAMBLE:
            return "RACH_PREAMBLE";
        case NrControlMessage::RAR:
            return "RAR";
        case NrControlMessage::BSR:
            return "BSR";
        case NrControlMessage::DL_HARQ:
            return "DL_HARQ";
        case NrControlMessage::SR:
            return "SR";
        case NrControlMessage::SRS:
            return "SRS";
    }
    return "UNKNOWN";
}

inline void
DlRxTbTraceCallback(Ptr<OutputStreamWrapper> stream, std::string context, RxPacketTraceParams params)
{
    if (!IsStreamReady(stream))
    {
        return;
    }
    (void)context;

    *stream->GetStream() << Simulator::Now().GetMicroSeconds() << "\t" << params.m_frameNum << "\t"
                         << static_cast<uint32_t>(params.m_subframeNum) << "\t"
                         << static_cast<uint32_t>(params.m_slotNum) << "\t"
                         << static_cast<uint32_t>(params.m_symStart) << "\t"
                         << static_cast<uint32_t>(params.m_numSym) << "\t" << params.m_cellId
                         << "\t" << static_cast<uint32_t>(params.m_bwpId) << "\t" << params.m_rnti
                         << "\t" << params.m_tbSize << "\t" << static_cast<uint32_t>(params.m_mcs)
                         << "\t" << static_cast<uint32_t>(params.m_rank) << "\t"
                         << static_cast<uint32_t>(params.m_rv) << "\t" << 10 * log10(params.m_sinr)
                         << "\t" << static_cast<uint32_t>(params.m_cqi) << "\t" << params.m_corrupt
                         << "\t" << params.m_tbler << std::endl;
}

inline void
UlRxTbTraceCallback(Ptr<OutputStreamWrapper> stream, std::string context, RxPacketTraceParams params)
{
    if (!IsStreamReady(stream))
    {
        return;
    }
    (void)context;

    *stream->GetStream() << Simulator::Now().GetMicroSeconds() << "\t" << params.m_frameNum << "\t"
                         << static_cast<uint32_t>(params.m_subframeNum) << "\t"
                         << static_cast<uint32_t>(params.m_slotNum) << "\t"
                         << static_cast<uint32_t>(params.m_symStart) << "\t"
                         << static_cast<uint32_t>(params.m_numSym) << "\t" << params.m_cellId
                         << "\t" << static_cast<uint32_t>(params.m_bwpId) << "\t" << params.m_rnti
                         << "\t" << params.m_tbSize << "\t" << static_cast<uint32_t>(params.m_mcs)
                         << "\t" << static_cast<uint32_t>(params.m_rank) << "\t"
                         << static_cast<uint32_t>(params.m_rv) << "\t" << 10 * log10(params.m_sinr)
                         << "\t" << static_cast<uint32_t>(params.m_cqi) << "\t" << params.m_corrupt
                         << "\t" << params.m_tbler << std::endl;
}

inline void
DlRxTbComponentTraceCallback(Ptr<OutputStreamWrapper> stream,
                             std::string context,
                             RxPacketTraceParams params,
                             uint8_t lcid,
                             uint64_t rxPduId,
                             uint32_t rxPduBytes,
                             uint32_t pktId,
                             uint32_t componentBytes)
{
    (void)context;
    WriteRxTbComponentTrace(
        stream, params, lcid, rxPduId, rxPduBytes, pktId, componentBytes);
}

inline void
UlRxTbComponentTraceCallback(Ptr<OutputStreamWrapper> stream,
                             std::string context,
                             RxPacketTraceParams params,
                             uint8_t lcid,
                             uint64_t rxPduId,
                             uint32_t rxPduBytes,
                             uint32_t pktId,
                             uint32_t componentBytes)
{
    (void)context;
    WriteRxTbComponentTrace(
        stream, params, lcid, rxPduId, rxPduBytes, pktId, componentBytes);
}

inline void
MacTbDelayTraceCallback(Ptr<OutputStreamWrapper> stream,
                        std::string context,
                        uint16_t cellId,
                        uint16_t rnti,
                        uint8_t bwpId,
                        bool isDownlink,
                        uint64_t delayNs,
                        uint32_t ipId)
{
    if (!IsStreamReady(stream))
    {
        return;
    }
    (void)isDownlink;
    (void)context;

    const uint64_t delayUs = delayNs / 1000;
    *stream->GetStream() << Simulator::Now().GetMicroSeconds() << "\t" << cellId << "\t"
                         << static_cast<uint32_t>(bwpId) << "\t" << rnti << "\t" << ipId << "\t"
                         << delayUs << std::endl;
}

inline void
DlDataSinrTraceCallback(Ptr<OutputStreamWrapper> stream,
                        std::string context,
                        uint16_t cellId,
                        uint16_t rnti,
                        double avgSinr,
                        uint16_t bwpId)
{
    (void)context;
    WriteUeSinrTrace(stream, cellId, rnti, avgSinr, bwpId);
}

inline void
DlCtrlSinrTraceCallback(Ptr<OutputStreamWrapper> stream,
                        std::string context,
                        uint16_t cellId,
                        uint16_t rnti,
                        double avgSinr,
                        uint16_t bwpId)
{
    (void)context;
    WriteUeSinrTrace(stream, cellId, rnti, avgSinr, bwpId);
}

inline void
DlPdcpRxTraceCallback(Ptr<OutputStreamWrapper> stream,
                      std::string context,
                      uint16_t rnti,
                      uint8_t lcid,
                      uint32_t packetSize,
                      uint64_t delay,
                      uint32_t ipId)
{
    const uint16_t cellId = ResolveCellIdFromContext(context);
    WriteRxPduTrace(stream, cellId, rnti, lcid, ipId, packetSize, delay);
}

inline void
DlPdcpTxTraceCallback(Ptr<OutputStreamWrapper> stream,
                      std::string context,
                      uint16_t rnti,
                      uint8_t lcid,
                      uint32_t packetSize,
                      uint32_t ipId)
{
    (void)context;
    const uint16_t cellId = ResolveCellIdFromRnti(rnti);
    WriteTxPduTrace(stream, cellId, rnti, lcid, ipId, packetSize);
}

inline void
UlPdcpRxTraceCallback(Ptr<OutputStreamWrapper> stream,
                      std::string context,
                      uint16_t rnti,
                      uint8_t lcid,
                      uint32_t packetSize,
                      uint64_t delay,
                      uint32_t ipId)
{
    (void)context;
    const uint16_t cellId = ResolveCellIdFromRnti(rnti);
    WriteRxPduTrace(stream, cellId, rnti, lcid, ipId, packetSize, delay);
}

inline void
UlPdcpTxTraceCallback(Ptr<OutputStreamWrapper> stream,
                      std::string context,
                      uint16_t rnti,
                      uint8_t lcid,
                      uint32_t packetSize,
                      uint32_t ipId)
{
    const uint16_t cellId = ResolveCellIdFromContext(context);
    WriteTxPduTrace(stream, cellId, rnti, lcid, ipId, packetSize);
}

inline void
DlRlcRxTraceCallback(Ptr<OutputStreamWrapper> stream,
                     std::string context,
                     uint16_t rnti,
                     uint8_t lcid,
                     uint32_t packetSize,
                     uint64_t delay,
                     uint32_t ipId)
{
    const uint16_t cellId = ResolveCellIdFromContext(context);
    WriteRxPduTrace(stream, cellId, rnti, lcid, ipId, packetSize, delay);
}

inline void
DlRlcRxComponentTraceCallback(Ptr<OutputStreamWrapper> stream,
                              std::string context,
                              uint16_t rnti,
                              uint8_t lcid,
                              uint16_t rlcSn,
                              uint32_t rlcPduBytes,
                              uint32_t pktId,
                              uint32_t componentBytes,
                              uint64_t delayNs)
{
    const uint16_t cellId = ResolveCellIdFromContext(context);
    WriteRxPduComponentTrace(stream,
                             cellId,
                             rnti,
                             lcid,
                             rlcSn,
                             rlcPduBytes,
                             pktId,
                             componentBytes,
                             delayNs);
}

inline void
DlRlcTxTraceCallback(Ptr<OutputStreamWrapper> stream,
                     std::string context,
                     uint16_t rnti,
                     uint8_t lcid,
                     uint32_t packetSize,
                     uint32_t ipId)
{
    (void)context;
    const uint16_t cellId = ResolveCellIdFromRnti(rnti);
    WriteTxPduTrace(stream, cellId, rnti, lcid, ipId, packetSize);
}

inline void
DlRlcTxComponentTraceCallback(Ptr<OutputStreamWrapper> stream,
                              std::string context,
                              uint16_t rnti,
                              uint8_t lcid,
                              uint16_t rlcSn,
                              uint32_t rlcPduBytes,
                              uint32_t pktId,
                              uint32_t componentBytes)
{
    (void)context;
    const uint16_t cellId = ResolveCellIdFromRnti(rnti);
    WriteTxPduComponentTrace(
        stream, cellId, rnti, lcid, rlcSn, rlcPduBytes, pktId, componentBytes);
}

inline void
UlRlcRxTraceCallback(Ptr<OutputStreamWrapper> stream,
                     std::string context,
                     uint16_t rnti,
                     uint8_t lcid,
                     uint32_t packetSize,
                     uint64_t delay,
                     uint32_t ipId)
{
    (void)context;
    const uint16_t cellId = ResolveCellIdFromRnti(rnti);
    WriteRxPduTrace(stream, cellId, rnti, lcid, ipId, packetSize, delay);
}

inline void
UlRlcRxComponentTraceCallback(Ptr<OutputStreamWrapper> stream,
                              std::string context,
                              uint16_t rnti,
                              uint8_t lcid,
                              uint16_t rlcSn,
                              uint32_t rlcPduBytes,
                              uint32_t pktId,
                              uint32_t componentBytes,
                              uint64_t delayNs)
{
    (void)context;
    const uint16_t cellId = ResolveCellIdFromRnti(rnti);
    WriteRxPduComponentTrace(stream,
                             cellId,
                             rnti,
                             lcid,
                             rlcSn,
                             rlcPduBytes,
                             pktId,
                             componentBytes,
                             delayNs);
}

inline void
UlRlcTxTraceCallback(Ptr<OutputStreamWrapper> stream,
                     std::string context,
                     uint16_t rnti,
                     uint8_t lcid,
                     uint32_t packetSize,
                     uint32_t ipId)
{
    const uint16_t cellId = ResolveCellIdFromContext(context);
    WriteTxPduTrace(stream, cellId, rnti, lcid, ipId, packetSize);
}

inline void
UlRlcTxComponentTraceCallback(Ptr<OutputStreamWrapper> stream,
                              std::string context,
                              uint16_t rnti,
                              uint8_t lcid,
                              uint16_t rlcSn,
                              uint32_t rlcPduBytes,
                              uint32_t pktId,
                              uint32_t componentBytes)
{
    const uint16_t cellId = ResolveCellIdFromContext(context);
    WriteTxPduComponentTrace(
        stream, cellId, rnti, lcid, rlcSn, rlcPduBytes, pktId, componentBytes);
}

inline void
RlcHolDelayTraceCallback(Ptr<OutputStreamWrapper> stream,
                         std::string context,
                         uint16_t rnti,
                         uint8_t lcid,
                         uint32_t txQueueSize,
                         uint16_t txQueueHolDelay,
                         uint32_t retxQueueSize,
                         uint16_t retxQueueHolDelay,
                         uint16_t statusPduSize)
{
    if (!IsStreamReady(stream))
    {
        return;
    }

    const uint16_t cellId = ResolveCellIdFromContext(context);
    const uint64_t nowMicros = Simulator::Now().GetMicroSeconds();
    const uint64_t txHolMicros = static_cast<uint64_t>(txQueueHolDelay) * 1000;
    const uint64_t retxHolMicros = static_cast<uint64_t>(retxQueueHolDelay) * 1000;

    *stream->GetStream() << nowMicros << "\t" << cellId << "\t" << rnti << "\t"
                         << static_cast<uint32_t>(lcid) << "\t" << txQueueSize << "\t"
                         << txHolMicros << "\t" << retxQueueSize << "\t" << retxHolMicros << "\t"
                         << statusPduSize << std::endl;
}

inline void
RlcTxQueueSojournTraceCallback(Ptr<OutputStreamWrapper> stream,
                               std::string context,
                               uint16_t rnti,
                               uint8_t lcid,
                               uint32_t pduSize,
                               uint64_t sojournNs,
                               uint32_t ipId)
{
    if (!IsStreamReady(stream))
    {
        return;
    }

    const uint16_t cellId = ResolveCellIdFromContext(context);
    const uint64_t nowMicros = Simulator::Now().GetMicroSeconds();
    const uint64_t sojournMicros = sojournNs / 1000;

    *stream->GetStream() << nowMicros << "\t" << cellId << "\t" << rnti << "\t"
                         << static_cast<uint32_t>(lcid) << "\t" << ipId << "\t" << pduSize
                         << "\t" << sojournMicros << std::endl;
}

inline void
RlcHolGrantWaitTraceCallback(Ptr<OutputStreamWrapper> stream,
                             std::string context,
                             uint16_t rnti,
                             uint8_t lcid,
                             uint32_t pduSize,
                             uint64_t waitNs,
                             uint32_t ipId)
{
    if (!IsStreamReady(stream))
    {
        return;
    }

    const uint16_t cellId = ResolveCellIdFromContext(context);
    const uint64_t nowMicros = Simulator::Now().GetMicroSeconds();
    const uint64_t waitMicros = waitNs / 1000;

    *stream->GetStream() << nowMicros << "\t" << cellId << "\t" << rnti << "\t"
                         << static_cast<uint32_t>(lcid) << "\t" << ipId << "\t" << pduSize
                         << "\t" << waitMicros << std::endl;
}

inline void
RsrpRsrqTraceCallback(Ptr<OutputStreamWrapper> stream,
                      std::string context,
                      uint16_t rnti,
                      uint16_t measuredCellId,
                      double rsrp,
                      double rsrq,
                      bool isServingCell,
                      uint8_t bwpId)
{
    if (!IsStreamReady(stream))
    {
        return;
    }
    (void)rsrq;

    const uint16_t ueId = ResolveUeIdFromContext(context);
    const uint64_t imsi = GetImsi_from_ueId(ueId);
    const uint16_t cellId = GetCellId_from_ueId(ueId);
    const int64_t nowMicros = Simulator::Now().GetMicroSeconds();
    *stream->GetStream() << nowMicros << "\t" << ueId << "\t" << imsi << "\t" << cellId << "\t"
                         << measuredCellId << "\t" << static_cast<uint32_t>(bwpId) << "\t" << rnti
                         << "\t" << rsrp << "\t" << static_cast<uint32_t>(isServingCell)
                         << std::endl;
}

#endif // NR_TRACE_COMMON_H
