// Copyright (c) 2026
//
// SPDX-License-Identifier: GPL-2.0-only

#include "ns3/nr-ue-mac.h"
#include "ns3/simulator.h"
#include "ns3/test.h"
#include "ns3/uinteger.h"

namespace ns3
{

class NrUeMacRetxBsrTestCase : public TestCase
{
  public:
    NrUeMacRetxBsrTestCase()
        : TestCase("UE MAC retransmission BSR timer")
    {
    }

  private:
    void DoRun() override
    {
        Ptr<NrUeMac> mac = CreateObject<NrUeMac>();
        mac->SetAttribute("RetxBsrTimer", TimeValue(MilliSeconds(10)));

        NrMacSapProvider::BufferStatusReportParameters bsr{};
        bsr.rnti = 1;
        bsr.lcid = 4;
        bsr.txQueueSize = 100;

        mac->DoTransmitBufferStatusReport(bsr);
        NS_TEST_ASSERT_MSG_EQ(mac->m_srState,
                              NrUeMac::TO_SEND,
                              "New data in an idle UE did not request an immediate SR");

        mac->m_srState = NrUeMac::ACTIVE;
        mac->RestartRetxBsrTimer();
        Simulator::Schedule(MilliSeconds(5), &NrUeMac::RestartRetxBsrTimer, mac);

        bool activeBeforeRestartedDeadline = false;
        Simulator::Schedule(MilliSeconds(11), [&]() {
            activeBeforeRestartedDeadline = mac->m_srState == NrUeMac::ACTIVE;
        });
        Simulator::Stop(MilliSeconds(16));
        Simulator::Run();

        NS_TEST_ASSERT_MSG_EQ(activeBeforeRestartedDeadline,
                              true,
                              "Restarting the timer did not postpone recovery");
        NS_TEST_ASSERT_MSG_EQ(mac->m_srState,
                              NrUeMac::TO_SEND,
                              "Buffered data did not trigger recovery after timer expiry");
        Simulator::Destroy();

        mac = CreateObject<NrUeMac>();
        mac->SetAttribute("RetxBsrTimer", TimeValue(MilliSeconds(10)));
        mac->DoTransmitBufferStatusReport(bsr);
        mac->m_srState = NrUeMac::ACTIVE;
        mac->RestartRetxBsrTimer();

        bsr.txQueueSize = 0;
        mac->DoTransmitBufferStatusReport(bsr);
        NS_TEST_ASSERT_MSG_EQ(mac->m_srState,
                              NrUeMac::INACTIVE,
                              "An empty buffer did not return the UE to INACTIVE");
        NS_TEST_ASSERT_MSG_EQ(mac->m_retxBsrTimer.IsPending(),
                              false,
                              "An empty buffer did not cancel the retransmission BSR timer");
        Simulator::Destroy();

        mac = CreateObject<NrUeMac>();
        NS_TEST_ASSERT_MSG_EQ(mac->IsSrOpportunity(SfnSf(0, 0, 0, 1)),
                              true,
                              "Disabled SR periodicity did not preserve immediate SR behavior");
        mac->SetAttribute("SrPeriodicitySlots", UintegerValue(10));
        mac->SetAttribute("SrOffsetSlots", UintegerValue(5));
        NS_TEST_ASSERT_MSG_EQ(mac->IsSrOpportunity(SfnSf(0, 2, 1, 1)),
                              true,
                              "Configured SR offset was not accepted");
        NS_TEST_ASSERT_MSG_EQ(mac->IsSrOpportunity(SfnSf(0, 7, 1, 1)),
                              true,
                              "Configured SR opportunity did not repeat after one period");
        NS_TEST_ASSERT_MSG_EQ(mac->IsSrOpportunity(SfnSf(0, 3, 0, 1)),
                              false,
                              "A slot outside the configured SR grid was accepted");

        Ptr<NrUeMac> secondMac = CreateObject<NrUeMac>();
        secondMac->SetAttribute("SrPeriodicitySlots", UintegerValue(10));
        secondMac->SetAttribute("SrOffsetSlots", UintegerValue(6));
        NS_TEST_ASSERT_MSG_EQ(secondMac->IsSrOpportunity(SfnSf(0, 3, 0, 1)),
                              true,
                              "A second UE did not retain its independent SR offset");
        NS_TEST_ASSERT_MSG_EQ(mac->IsSrOpportunity(SfnSf(0, 3, 0, 1)),
                              false,
                              "Configuring a second UE changed the first UE's SR grid");
    }
};

class NrUeMacRetxBsrTestSuite : public TestSuite
{
  public:
    NrUeMacRetxBsrTestSuite()
        : TestSuite("nr-ue-mac-retx-bsr", Type::UNIT)
    {
        AddTestCase(new NrUeMacRetxBsrTestCase(), Duration::QUICK);
    }
};

static NrUeMacRetxBsrTestSuite g_nrUeMacRetxBsrTestSuite;

} // namespace ns3
