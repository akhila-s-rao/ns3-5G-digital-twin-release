/*
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * codex added: Tag to carry pkt_id for cross-layer tracing.
 */

#ifndef IPV4_ID_TAG_H
#define IPV4_ID_TAG_H

#include "ns3/tag.h"

#include <cstdint>

namespace ns3
{

/**
 * @ingroup ipv4
 *
 * @brief Tag carrying the pkt_id field for cross-layer tracing.
 */
class Ipv4IdTag : public Tag
{
  public:
    Ipv4IdTag();
    explicit Ipv4IdTag(uint32_t id);

    /**
     * @brief Set the pkt_id value.
     *
     * @param id The pkt_id.
     */
    void SetId(uint32_t id);

    /**
     * @brief Get the pkt_id value.
     *
     * @return The pkt_id.
     */
    uint32_t GetId() const;

    static TypeId GetTypeId();
    TypeId GetInstanceTypeId() const override;
    uint32_t GetSerializedSize() const override;
    void Serialize(TagBuffer i) const override;
    void Deserialize(TagBuffer i) override;
    void Print(std::ostream& os) const override;

  private:
    uint32_t m_id{0};
};

} // namespace ns3

#endif // IPV4_ID_TAG_H
