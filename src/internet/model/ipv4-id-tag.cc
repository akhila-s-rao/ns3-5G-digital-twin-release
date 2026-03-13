/*
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * codex added: Tag to carry pkt_id for cross-layer tracing.
 */

#include "ipv4-id-tag.h"

#include "ns3/log.h"

namespace ns3
{

NS_LOG_COMPONENT_DEFINE("Ipv4IdTag");

Ipv4IdTag::Ipv4IdTag()
    : m_id(0)
{
    NS_LOG_FUNCTION(this);
}

Ipv4IdTag::Ipv4IdTag(uint32_t id)
    : m_id(id)
{
    NS_LOG_FUNCTION(this << id);
}

void
Ipv4IdTag::SetId(uint32_t id)
{
    NS_LOG_FUNCTION(this << id);
    m_id = id;
}

uint32_t
Ipv4IdTag::GetId() const
{
    NS_LOG_FUNCTION(this);
    return m_id;
}

TypeId
Ipv4IdTag::GetTypeId()
{
    static TypeId tid = TypeId("ns3::Ipv4IdTag")
                            .SetParent<Tag>()
                            .SetGroupName("Internet")
                            .AddConstructor<Ipv4IdTag>();
    return tid;
}

TypeId
Ipv4IdTag::GetInstanceTypeId() const
{
    NS_LOG_FUNCTION(this);
    return GetTypeId();
}

uint32_t
Ipv4IdTag::GetSerializedSize() const
{
    NS_LOG_FUNCTION(this);
    return sizeof(uint32_t);
}

void
Ipv4IdTag::Serialize(TagBuffer i) const
{
    NS_LOG_FUNCTION(this << &i);
    i.WriteU32(m_id);
}

void
Ipv4IdTag::Deserialize(TagBuffer i)
{
    NS_LOG_FUNCTION(this << &i);
    m_id = i.ReadU32();
}

void
Ipv4IdTag::Print(std::ostream& os) const
{
    NS_LOG_FUNCTION(this << &os);
    os << "pkt_id=" << m_id;
}

} // namespace ns3
