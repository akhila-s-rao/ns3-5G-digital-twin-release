// Copyright (c) 2024
//
// SPDX-License-Identifier: GPL-2.0-only
//
// codex added: Tag implementation for MAC first-TX timestamp.

#include "nr-mac-tx-time-tag.h"

#include "ns3/tag.h"

namespace ns3
{

NS_OBJECT_ENSURE_REGISTERED(NrMacTxTimeTag);

NrMacTxTimeTag::NrMacTxTimeTag()
    : m_txTime(Seconds(0))
{
}

NrMacTxTimeTag::NrMacTxTimeTag(Time txTime)
    : m_txTime(txTime)
{
}

TypeId
NrMacTxTimeTag::GetTypeId()
{
    static TypeId tid =
        TypeId("ns3::NrMacTxTimeTag").SetParent<Tag>().SetGroupName("Nr").AddConstructor<NrMacTxTimeTag>();
    return tid;
}

TypeId
NrMacTxTimeTag::GetInstanceTypeId() const
{
    return GetTypeId();
}

uint32_t
NrMacTxTimeTag::GetSerializedSize() const
{
    return sizeof(int64_t);
}

void
NrMacTxTimeTag::Serialize(TagBuffer i) const
{
    int64_t txTimeNs = m_txTime.GetNanoSeconds();
    i.Write((const uint8_t*)&txTimeNs, sizeof(int64_t));
}

void
NrMacTxTimeTag::Deserialize(TagBuffer i)
{
    int64_t txTimeNs;
    i.Read((uint8_t*)&txTimeNs, sizeof(int64_t));
    m_txTime = NanoSeconds(txTimeNs);
}

void
NrMacTxTimeTag::Print(std::ostream& os) const
{
    os << m_txTime;
}

} // namespace ns3
