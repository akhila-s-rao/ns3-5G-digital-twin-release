// Copyright (c) 2024
//
// SPDX-License-Identifier: GPL-2.0-only
//
// codex added: Tag to carry MAC first-TX timestamp for TB delay logging.

#ifndef NR_MAC_TX_TIME_TAG_H
#define NR_MAC_TX_TIME_TAG_H

#include "ns3/nstime.h"
#include "ns3/packet.h"

namespace ns3
{

class Tag;

/**
 * @brief Tag that stores the first MAC->PHY TX time for a TB.
 *
 * This is used to compute MAC-level TB delay at the receiver (after HARQ).
 */
class NrMacTxTimeTag : public Tag
{
  public:
    static TypeId GetTypeId();
    TypeId GetInstanceTypeId() const override;

    NrMacTxTimeTag();
    explicit NrMacTxTimeTag(Time txTime);

    void Serialize(TagBuffer i) const override;
    void Deserialize(TagBuffer i) override;
    uint32_t GetSerializedSize() const override;
    void Print(std::ostream& os) const override;

    Time GetTxTime() const
    {
        return m_txTime;
    }

    void SetTxTime(Time txTime)
    {
        m_txTime = txTime;
    }

  private:
    Time m_txTime; // codex added
};

} // namespace ns3

#endif // NR_MAC_TX_TIME_TAG_H
