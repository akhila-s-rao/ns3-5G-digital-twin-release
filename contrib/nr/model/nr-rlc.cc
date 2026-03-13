// Copyright (c) 2011 Centre Tecnologic de Telecomunicacions de Catalunya (CTTC)
//
// SPDX-License-Identifier: GPL-2.0-only
//
// Author: Nicola Baldo <nbaldo@cttc.es>

#include "nr-rlc.h"

#include "nr-rlc-sap.h"
#include "nr-rlc-tag.h"
// #include "nr-mac-sap.h"
// #include "nr-ff-mac-sched-sap.h"

#include "ns3/ipv4-id-tag.h" // codex added
#include "ns3/log.h"
#include "ns3/simulator.h"

namespace ns3
{

NS_LOG_COMPONENT_DEFINE("NrRlc");

/// NrRlcSpecificNrMacSapUser class
class NrRlcSpecificNrMacSapUser : public NrMacSapUser
{
  public:
    /**
     * Constructor
     *
     * @param rlc the RLC
     */
    NrRlcSpecificNrMacSapUser(NrRlc* rlc);

    // Interface implemented from NrMacSapUser
    void NotifyTxOpportunity(NrMacSapUser::TxOpportunityParameters params) override;
    void NotifyHarqDeliveryFailure() override;
    void ReceivePdu(NrMacSapUser::ReceivePduParameters params) override;

  private:
    NrRlcSpecificNrMacSapUser();
    NrRlc* m_rlc; ///< the RLC
};

NrRlcSpecificNrMacSapUser::NrRlcSpecificNrMacSapUser(NrRlc* rlc)
    : m_rlc(rlc)
{
}

NrRlcSpecificNrMacSapUser::NrRlcSpecificNrMacSapUser()
{
}

void
NrRlcSpecificNrMacSapUser::NotifyTxOpportunity(TxOpportunityParameters params)
{
    m_rlc->DoNotifyTxOpportunity(params);
}

void
NrRlcSpecificNrMacSapUser::NotifyHarqDeliveryFailure()
{
    m_rlc->DoNotifyHarqDeliveryFailure();
}

void
NrRlcSpecificNrMacSapUser::ReceivePdu(NrMacSapUser::ReceivePduParameters params)
{
    m_rlc->DoReceivePdu(params);
}

///////////////////////////////////////

NS_OBJECT_ENSURE_REGISTERED(NrRlc);

NrRlc::NrRlc()
    : m_rlcSapUser(nullptr),
      m_macSapProvider(nullptr),
      m_rnti(0),
      m_lcid(0)
{
    NS_LOG_FUNCTION(this);
    m_rlcSapProvider = new NrRlcSpecificNrRlcSapProvider<NrRlc>(this);
    m_macSapUser = new NrRlcSpecificNrMacSapUser(this);
}

NrRlc::~NrRlc()
{
    NS_LOG_FUNCTION(this);
}

TypeId
NrRlc::GetTypeId()
{
    static TypeId tid = TypeId("ns3::NrRlc")
                            .SetParent<Object>()
                            .SetGroupName("Nr")
                            .AddTraceSource("TxPDU",
                                            "PDU transmission notified to the MAC.",
                                            MakeTraceSourceAccessor(&NrRlc::m_txPdu),
                                            "ns3::NrRlc::NotifyTxTracedCallback")
                            .AddTraceSource("RxPDU",
                                            "PDU received.",
                                            MakeTraceSourceAccessor(&NrRlc::m_rxPdu),
                                            "ns3::NrRlc::ReceiveTracedCallback")
                            .AddTraceSource("TxPDUComponents",
                                            "Component-level rows for each transmitted RLC PDU.",
                                            MakeTraceSourceAccessor(&NrRlc::m_txPduComponents),
                                            "ns3::NrRlc::NotifyTxComponentsTracedCallback")
                            .AddTraceSource("RxPDUComponents",
                                            "Component-level rows for each received RLC PDU.",
                                            MakeTraceSourceAccessor(&NrRlc::m_rxPduComponents),
                                            "ns3::NrRlc::ReceiveComponentsTracedCallback")
                            // codex added
                            .AddTraceSource("BufferStatus",
                                            "RLC buffer status report.",
                                            MakeTraceSourceAccessor(&NrRlc::m_bufferStatus),
                                            "ns3::NrRlc::BufferStatusTracedCallback")
                            // codex added
                            .AddTraceSource("TxQueueSojourn",
                                            "Per-PDU/segment sojourn time in the RLC TX queue.",
                                            MakeTraceSourceAccessor(&NrRlc::m_txQueueSojourn),
                                            "ns3::NrRlc::TxQueueSojournTracedCallback")
                            // codex added
                            .AddTraceSource("TxHolGrantWait",
                                            "Per-PDU/segment HOL-to-grant wait time in the RLC TX queue.",
                                            MakeTraceSourceAccessor(&NrRlc::m_txHolGrantWait),
                                            "ns3::NrRlc::TxHolGrantWaitTracedCallback")
                            .AddTraceSource("TxDrop",
                                            "Trace source indicating a packet "
                                            "has been dropped before transmission",
                                            MakeTraceSourceAccessor(&NrRlc::m_txDropTrace),
                                            "ns3::Packet::TracedCallback");
    return tid;
}

void
NrRlc::DoDispose()
{
    NS_LOG_FUNCTION(this);
    delete (m_rlcSapProvider);
    delete (m_macSapUser);
}

void
NrRlc::TraceTxPduComponents(Ptr<const Packet> pdu, uint16_t rlcSn)
{
    NS_LOG_FUNCTION(this << pdu << rlcSn);
    if (!pdu)
    {
        return;
    }

    const uint32_t pduBytes = pdu->GetSize();
    bool emitted = false;
    for (ByteTagIterator it = pdu->GetByteTagIterator(); it.HasNext();)
    {
        auto item = it.Next();
        if (item.GetTypeId() != Ipv4IdTag::GetTypeId())
        {
            continue;
        }

        Ipv4IdTag ipIdTag;
        item.GetTag(ipIdTag);
        const uint32_t componentBytes =
            (item.GetEnd() >= item.GetStart()) ? (item.GetEnd() - item.GetStart()) : 0;
        m_txPduComponents(m_rnti, m_lcid, rlcSn, pduBytes, ipIdTag.GetId(), componentBytes);
        emitted = true;
    }

    if (!emitted)
    {
        m_txPduComponents(m_rnti, m_lcid, rlcSn, pduBytes, 0, pduBytes);
    }
}

void
NrRlc::TraceRxPduComponents(Ptr<const Packet> pdu, uint16_t rlcSn, uint64_t delayNs)
{
    NS_LOG_FUNCTION(this << pdu << rlcSn << delayNs);
    if (!pdu)
    {
        return;
    }

    const uint32_t pduBytes = pdu->GetSize();
    bool emitted = false;
    for (ByteTagIterator it = pdu->GetByteTagIterator(); it.HasNext();)
    {
        auto item = it.Next();
        if (item.GetTypeId() != Ipv4IdTag::GetTypeId())
        {
            continue;
        }

        Ipv4IdTag ipIdTag;
        item.GetTag(ipIdTag);
        const uint32_t componentBytes =
            (item.GetEnd() >= item.GetStart()) ? (item.GetEnd() - item.GetStart()) : 0;
        m_rxPduComponents(m_rnti,
                          m_lcid,
                          rlcSn,
                          pduBytes,
                          ipIdTag.GetId(),
                          componentBytes,
                          delayNs);
        emitted = true;
    }

    if (!emitted)
    {
        m_rxPduComponents(m_rnti, m_lcid, rlcSn, pduBytes, 0, pduBytes, delayNs);
    }
}

void
NrRlc::SetRnti(uint16_t rnti)
{
    NS_LOG_FUNCTION(this << (uint32_t)rnti);
    m_rnti = rnti;
}

void
NrRlc::SetLcId(uint8_t lcId)
{
    NS_LOG_FUNCTION(this << (uint32_t)lcId);
    m_lcid = lcId;
}

void
NrRlc::SetPacketDelayBudgetMs(uint16_t packetDelayBudget)
{
    NS_LOG_FUNCTION(this << +packetDelayBudget);
    m_packetDelayBudgetMs = packetDelayBudget;
}

void
NrRlc::SetNrRlcSapUser(NrRlcSapUser* s)
{
    NS_LOG_FUNCTION(this << s);
    m_rlcSapUser = s;
}

NrRlcSapProvider*
NrRlc::GetNrRlcSapProvider()
{
    NS_LOG_FUNCTION(this);
    return m_rlcSapProvider;
}

void
NrRlc::SetNrMacSapProvider(NrMacSapProvider* s)
{
    NS_LOG_FUNCTION(this << s);
    m_macSapProvider = s;
}

NrMacSapUser*
NrRlc::GetNrMacSapUser()
{
    NS_LOG_FUNCTION(this);
    return m_macSapUser;
}

////////////////////////////////////////

NS_OBJECT_ENSURE_REGISTERED(NrRlcSm);

NrRlcSm::NrRlcSm()
{
    NS_LOG_FUNCTION(this);
}

NrRlcSm::~NrRlcSm()
{
    NS_LOG_FUNCTION(this);
}

TypeId
NrRlcSm::GetTypeId()
{
    static TypeId tid =
        TypeId("ns3::NrRlcSm").SetParent<NrRlc>().SetGroupName("Nr").AddConstructor<NrRlcSm>();
    return tid;
}

void
NrRlcSm::DoInitialize()
{
    NS_LOG_FUNCTION(this);
    BufferStatusReport();
}

void
NrRlcSm::DoDispose()
{
    NS_LOG_FUNCTION(this);
    NrRlc::DoDispose();
}

void
NrRlcSm::DoTransmitPdcpPdu(Ptr<Packet> p)
{
    NS_LOG_FUNCTION(this << p);
}

void
NrRlcSm::DoReceivePdu(NrMacSapUser::ReceivePduParameters rxPduParams)
{
    NS_LOG_FUNCTION(this << rxPduParams.p);
    // RLC Performance evaluation
    NrRlcTag rlcTag;
    Time delay;
    bool ret = rxPduParams.p->FindFirstMatchingByteTag(rlcTag);
    NS_ASSERT_MSG(ret, "NrRlcTag is missing");
    delay = Simulator::Now() - rlcTag.GetSenderTimestamp();
    NS_LOG_LOGIC(" RNTI=" << m_rnti << " LCID=" << (uint32_t)m_lcid << " size="
                          << rxPduParams.p->GetSize() << " delay=" << delay.As(Time::NS));
    // codex added: propagate IPv4 identification in RLC traces when present.
    Ipv4IdTag ipIdTag;
    const uint32_t ipId = rxPduParams.p->FindFirstMatchingByteTag(ipIdTag) ? ipIdTag.GetId() : 0;
    m_rxPdu(m_rnti, m_lcid, rxPduParams.p->GetSize(), delay.GetNanoSeconds(), ipId);
    TraceRxPduComponents(rxPduParams.p, 0, delay.GetNanoSeconds());
}

void
NrRlcSm::DoNotifyTxOpportunity(NrMacSapUser::TxOpportunityParameters txOpParams)
{
    NS_LOG_FUNCTION(this << txOpParams.bytes);
    NrMacSapProvider::TransmitPduParameters params;
    NrRlcTag tag(Simulator::Now());

    params.pdu = Create<Packet>(txOpParams.bytes);
    NS_ABORT_MSG_UNLESS(txOpParams.bytes > 0, "Bytes must be > 0");
    /**
     * For RLC SM, the packets are not passed to the upper layers, therefore,
     * in the absence of an header we can safely byte tag the entire packet.
     */
    params.pdu->AddByteTag(tag, 1, params.pdu->GetSize());

    params.rnti = m_rnti;
    params.lcid = m_lcid;
    params.layer = txOpParams.layer;
    params.harqProcessId = txOpParams.harqId;
    params.componentCarrierId = txOpParams.componentCarrierId;

    // RLC Performance evaluation
    NS_LOG_LOGIC(" RNTI=" << m_rnti << " LCID=" << (uint32_t)m_lcid
                          << " size=" << txOpParams.bytes);
    // codex added: RLC SM does not carry IP tags; log ip_id as 0.
    m_txPdu(m_rnti, m_lcid, txOpParams.bytes, 0);
    TraceTxPduComponents(params.pdu, 0);

    m_macSapProvider->TransmitPdu(params);
    BufferStatusReport();
}

void
NrRlcSm::DoNotifyHarqDeliveryFailure()
{
    NS_LOG_FUNCTION(this);
}

void
NrRlcSm::BufferStatusReport()
{
    NS_LOG_FUNCTION(this);
    NrMacSapProvider::BufferStatusReportParameters p;
    p.rnti = m_rnti;
    p.lcid = m_lcid;
    p.txQueueSize = 80000;
    p.txQueueHolDelay = 10;
    p.retxQueueSize = 0;
    p.retxQueueHolDelay = 0;
    p.statusPduSize = 0;
    p.expBsrTimer = false;
    // codex added
    m_bufferStatus(p.rnti,
                   p.lcid,
                   p.txQueueSize,
                   p.txQueueHolDelay,
                   p.retxQueueSize,
                   p.retxQueueHolDelay,
                   p.statusPduSize);
    m_macSapProvider->BufferStatusReport(p);
}

//////////////////////////////////////////

// NrRlcTm::~NrRlcTm ()
// {
// }

//////////////////////////////////////////

// NrRlcUm::~NrRlcUm ()
// {
// }

//////////////////////////////////////////

// NrRlcAm::~NrRlcAm ()
// {
// }

} // namespace ns3
