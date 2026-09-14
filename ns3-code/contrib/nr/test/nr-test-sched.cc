// Copyright (c) 2019 Centre Tecnologic de Telecomunicacions de Catalunya (CTTC)
//
// SPDX-License-Identifier: GPL-2.0-only

#include "ns3/nr-mac-sched-sap.h"
#include "ns3/nr-mac-scheduler-ns3.h"
#include "ns3/object-factory.h"
#include "ns3/test.h"

/**
 * @file nr-test-sched.cc
 * @ingroup test
 *
 * @brief The class is a stub for a future, unit-testing component for the various
 * kind of schedulers. The idea is to check what is happening to the scheduling
 * part following a black-box approach: passing inputs, and then see what
 * is the output, and if it is like we would expect. The reference API is the
 * FF API, and we should check what happens, for example, when adding or
 * removing users, when a CQI is passed, etc.
 */
namespace ns3
{

/**
 * @ingroup test
 * @brief The TestCschedSapUser class
 *
 * This class doesn't do absolutely nothing. Thank you for the attention.
 */
class TestCschedSapUser : public NrMacCschedSapUser
{
  public:
    TestCschedSapUser()
        : NrMacCschedSapUser()
    {
    }

    void CschedCellConfigCnf(
        [[maybe_unused]] const struct CschedCellConfigCnfParameters& params) override
    {
    }

    void CschedUeConfigCnf(
        [[maybe_unused]] const struct CschedUeConfigCnfParameters& params) override
    {
    }

    void CschedLcConfigCnf(
        [[maybe_unused]] const struct CschedLcConfigCnfParameters& params) override
    {
    }

    void CschedLcReleaseCnf(
        [[maybe_unused]] const struct CschedLcReleaseCnfParameters& params) override
    {
    }

    void CschedUeReleaseCnf(
        [[maybe_unused]] const struct CschedUeReleaseCnfParameters& params) override
    {
    }

    void CschedUeConfigUpdateInd(
        [[maybe_unused]] const struct CschedUeConfigUpdateIndParameters& params) override
    {
    }

    void CschedCellConfigUpdateInd(
        [[maybe_unused]] const struct CschedCellConfigUpdateIndParameters& params) override
    {
    }
};

class TestSchedSapUser;

/**
 * @brief TestSched testcase
 */
class NrSchedGeneralTestCase : public TestCase
{
  public:
    /**
     * @brief Create NrSchedGeneralTestCase
     * @param scheduler Scheduler to test
     * @param name Name of the test
     */
    NrSchedGeneralTestCase(const std::string& scheduler, const std::string& name)
        : TestCase(name),
          m_scheduler(scheduler)
    {
    }

    /**
     * @brief Destroy the object instance
     */
    ~NrSchedGeneralTestCase() override
    {
    }

    void SchedConfigInd(const struct NrMacSchedSapUser::SchedConfigIndParameters& params);

  protected:
    void TestSAPInterface(const Ptr<NrMacScheduler>& sched);
    void TestAddingRemovingUsersNoData(const Ptr<NrMacSchedulerNs3>& sched);
    void TestSchedNewData(const Ptr<NrMacSchedulerNs3>& sched);
    void TestSchedNewDlData(const Ptr<NrMacSchedulerNs3>& sched);
    void TestSchedNewUlData(const Ptr<NrMacSchedulerNs3>& sched);
    void TestSchedNewDlUlData(const Ptr<NrMacSchedulerNs3>& sched);
    void TestUlMcsLimit(const Ptr<NrMacSchedulerNs3>& sched);
    void TestSrBootstrapClassification(const Ptr<NrMacSchedulerNs3>& sched);

  protected:
    void AddOneUser(uint16_t rnti, const Ptr<NrMacSchedulerNs3>& sched);
    void TestingRemovingUsers(const Ptr<NrMacSchedulerNs3>& sched);
    void TestingAddingUsers(const Ptr<NrMacSchedulerNs3>& sched);
    void LcConfigFor(uint16_t rnti, uint32_t bytes, const Ptr<NrMacSchedulerNs3>& sched);

  private:
    void DoRun() override;

    std::string m_scheduler{}; //!< Type of the scheduler
    TestCschedSapUser* m_cSchedSapUser{nullptr};
    TestSchedSapUser* m_schedSapUser{nullptr};
};

class TestSchedSapUser : public NrMacSchedSapUser
{
  public:
    TestSchedSapUser(NrSchedGeneralTestCase* testCase)
        : NrMacSchedSapUser(),
          m_testCase(testCase)
    {
    }

    void SchedConfigInd(const struct SchedConfigIndParameters& params) override
    {
        m_testCase->SchedConfigInd(params);
    }

    // For the rest, setup some hard-coded values; for the moment, there is
    // no need to have real values here.
    Ptr<const SpectrumModel> GetSpectrumModel() const override
    {
        return nullptr;
    }

    uint32_t GetNumRbPerRbg() const override
    {
        return 1;
    }

    uint8_t GetNumHarqProcess() const override
    {
        return 20;
    }

    uint16_t GetBwpId() const override
    {
        return 0;
    }

    uint16_t GetCellId() const override
    {
        return 0;
    }

    uint32_t GetSymbolsPerSlot() const override
    {
        return 14;
    }

    Time GetSlotPeriod() const override
    {
        return MilliSeconds(1);
    }

    void BuildRarList(SlotAllocInfo& allocInfo) override
    {
    }

  private:
    NrSchedGeneralTestCase* m_testCase;
};

void
NrSchedGeneralTestCase::TestSAPInterface(const Ptr<NrMacScheduler>& sched)
{
    NS_ABORT_IF(sched->GetMacSchedSapProvider() == nullptr);
    NS_ABORT_IF(sched->GetMacCschedSapProvider() == nullptr);
    sched->SetMacCschedSapUser(m_cSchedSapUser);
    sched->SetMacSchedSapUser(m_schedSapUser);
}

void
NrSchedGeneralTestCase::SchedConfigInd(
    [[maybe_unused]] const struct NrMacSchedSapUser::SchedConfigIndParameters& params)
{
}

void
NrSchedGeneralTestCase::AddOneUser(uint16_t rnti, const Ptr<NrMacSchedulerNs3>& sched)
{
    NrMacCschedSapProvider::CschedUeConfigReqParameters params;
    params.m_rnti = rnti;
    params.m_beamId = BeamId(8, 120.0);
    sched->DoCschedUeConfigReq(params);
}

void
NrSchedGeneralTestCase::TestingAddingUsers(const Ptr<NrMacSchedulerNs3>& sched)
{
    for (uint16_t i = 0; i < 80; ++i)
    {
        AddOneUser(i, sched);
        NS_TEST_ASSERT_MSG_EQ(sched->m_ueMap.size(),
                              static_cast<uint32_t>(i + 1),
                              "UE not saved in the map");
    }
}

void
NrSchedGeneralTestCase::TestingRemovingUsers(const Ptr<NrMacSchedulerNs3>& sched)
{
    for (uint16_t i = 80; i > 0; --i)
    {
        NrMacCschedSapProvider::CschedUeReleaseReqParameters params;
        params.m_rnti = i - 1;
        sched->DoCschedUeReleaseReq(params);
        NS_TEST_ASSERT_MSG_EQ(sched->m_ueMap.size(),
                              static_cast<uint32_t>(i - 1),
                              "UE released from the map. Map size " << sched->m_ueMap.size()
                                                                    << " counter " << i);
    }
}

void
NrSchedGeneralTestCase::TestAddingRemovingUsersNoData(const Ptr<NrMacSchedulerNs3>& sched)
{
    NS_TEST_ASSERT_MSG_EQ(sched->m_ueMap.size(), 0, "some UE are in the map");
    TestingAddingUsers(sched);
    TestingRemovingUsers(sched);
    NS_TEST_ASSERT_MSG_EQ(sched->m_ueMap.size(),
                          0,
                          sched->m_ueMap.size() << " UEs are still in the map");
}

void
NrSchedGeneralTestCase::TestSchedNewData(const Ptr<NrMacSchedulerNs3>& sched)
{
    TestSchedNewDlData(sched);
    TestSchedNewUlData(sched);
    TestSchedNewDlUlData(sched);
}

void
NrSchedGeneralTestCase::LcConfigFor(uint16_t rnti,
                                    uint32_t bytes,
                                    const Ptr<NrMacSchedulerNs3>& sched)
{
    NrMacCschedSapProvider::CschedLcConfigReqParameters params;
    nr::LogicalChannelConfigListElement_s lc;
    lc.m_logicalChannelIdentity = 1;
    lc.m_logicalChannelGroup = 0;
    lc.m_direction = nr::LogicalChannelConfigListElement_s::DIR_BOTH;
    lc.m_qosBearerType = nr::LogicalChannelConfigListElement_s::QBT_GBR;
    lc.m_qci = 1;
    lc.m_eRabMaximulBitrateUl = 0;
    lc.m_eRabMaximulBitrateDl = 0;
    lc.m_eRabGuaranteedBitrateUl = 0;
    lc.m_eRabGuaranteedBitrateDl = 0;
    params.m_rnti = rnti;
    params.m_reconfigureFlag = false;
    params.m_logicalChannelConfigList.emplace_back(lc);

    sched->DoCschedLcConfigReq(params);
}

void
NrSchedGeneralTestCase::TestSchedNewDlData(const Ptr<NrMacSchedulerNs3>& sched)
{
    // Add 80 users
    TestingAddingUsers(sched);
}

void
NrSchedGeneralTestCase::TestSchedNewUlData(const Ptr<NrMacSchedulerNs3>& sched)
{
}

void
NrSchedGeneralTestCase::TestSchedNewDlUlData(const Ptr<NrMacSchedulerNs3>& sched)
{
}

void
NrSchedGeneralTestCase::TestUlMcsLimit(const Ptr<NrMacSchedulerNs3>& sched)
{
    constexpr uint16_t rnti = 99;
    NS_TEST_ASSERT_MSG_EQ(sched->GetMaxUlMcs(), -1, "UL MCS limit should default to disabled");
    NS_TEST_ASSERT_MSG_EQ(sched->GetEffectiveUlMcs(rnti, 20),
                          20,
                          "Disabled UL MCS limit changed the estimated MCS");

    sched->SetMaxUlMcs(15);
    NS_TEST_ASSERT_MSG_EQ(sched->GetMaxUlMcs(), 15, "UL MCS limit was not stored");
    NS_TEST_ASSERT_MSG_EQ(sched->GetEffectiveUlMcs(rnti, 20),
                          15,
                          "UL MCS was not capped at the configured maximum");
    NS_TEST_ASSERT_MSG_EQ(sched->GetEffectiveUlMcs(rnti, 10),
                          10,
                          "UL MCS below the configured maximum was changed");

    sched->SetStartMcsUl(20);
    AddOneUser(rnti, sched);
    NS_TEST_ASSERT_MSG_EQ(sched->m_ueMap.at(rnti)->m_ulMcs,
                          15,
                          "A newly registered UE stored an uncapped UL MCS");

    sched->SetMaxUlMcs(12);
    NS_TEST_ASSERT_MSG_EQ(sched->m_ueMap.at(rnti)->m_ulMcs,
                          12,
                          "Changing the UL MCS limit did not cap existing UE state");

    sched->m_ueMap.at(rnti)->m_ulMcs = 20;
    sched->m_ueMap.at(rnti)->m_ulCqi.m_timer = 0;
    sched->m_cqiManagement.RefreshUlCqiMaps(sched->m_ueMap);
    NS_TEST_ASSERT_MSG_EQ(sched->m_ueMap.at(rnti)->m_ulMcs,
                          12,
                          "UL CQI expiry restored an uncapped starting MCS");

    NrMacCschedSapProvider::CschedUeReleaseReqParameters releaseParams;
    releaseParams.m_rnti = rnti;
    sched->DoCschedUeReleaseReq(releaseParams);
    sched->SetStartMcsUl(0);
    sched->SetMaxUlMcs(-1);
}

void
NrSchedGeneralTestCase::TestSrBootstrapClassification(const Ptr<NrMacSchedulerNs3>& sched)
{
    constexpr uint16_t rnti = 100;
    AddOneUser(rnti, sched);
    LcConfigFor(rnti, 0, sched);

    auto& ulLcgs = sched->m_ueMap.at(rnti)->m_ulLCG;
    NS_TEST_ASSERT_MSG_EQ(ulLcgs.size(), 1, "Expected one configured UL LCG");
    auto& lcg = ulLcgs.begin()->second;

    NrMacSchedulerNs3::PointInFTPlane spoint(0, 0);
    const std::list<uint16_t> srList{rnti};
    sched->m_enableBootstrapMcsLimit = true;

    lcg->UpdateInfo(4096);
    sched->DoScheduleUlSr(&spoint, srList);
    NS_TEST_ASSERT_MSG_EQ(lcg->GetTotalSize(),
                          4096,
                          "A recovery SR overwrote a positive UL buffer estimate");
    NS_TEST_ASSERT_MSG_EQ(sched->m_srBootstrapUesPending.count(rnti),
                          0,
                          "A recovery SR was incorrectly classified as bootstrap");
    NS_TEST_ASSERT_MSG_EQ(sched->GetEffectiveUlMcs(rnti, 20),
                          20,
                          "A recovery SR incorrectly enabled the bootstrap MCS cap");

    lcg->UpdateInfo(0);
    sched->DoScheduleUlSr(&spoint, srList);
    NS_TEST_ASSERT_MSG_EQ(lcg->GetTotalSize(), 12, "A bootstrap SR did not seed the UL estimate");
    NS_TEST_ASSERT_MSG_EQ(sched->m_srBootstrapUesPending.count(rnti),
                          1,
                          "A zero-estimate SR was not classified as bootstrap");
    NS_TEST_ASSERT_MSG_EQ(sched->GetEffectiveUlMcs(rnti, 20),
                          9,
                          "A bootstrap SR did not apply the configured MCS cap");
    NS_TEST_ASSERT_MSG_EQ(sched->GetUlBootstrapGrantRbgCount(),
                          5,
                          "A one-PRB RBG configuration did not produce a five-PRB bootstrap grant");

    sched->DoScheduleUlSr(&spoint, srList);
    NS_TEST_ASSERT_MSG_EQ(lcg->GetTotalSize(),
                          12,
                          "A repeated bootstrap SR changed the synthetic estimate");
    NS_TEST_ASSERT_MSG_EQ(sched->m_srBootstrapUesPending.count(rnti),
                          1,
                          "Bootstrap state did not remain pending until a grant");

    NrMacCschedSapProvider::CschedUeReleaseReqParameters releaseParams;
    releaseParams.m_rnti = rnti;
    sched->DoCschedUeReleaseReq(releaseParams);
    NS_TEST_ASSERT_MSG_EQ(sched->m_srBootstrapUesPending.count(rnti),
                          0,
                          "UE release left stale bootstrap state");
}

void
NrSchedGeneralTestCase::DoRun()
{
    m_cSchedSapUser = new TestCschedSapUser();
    m_schedSapUser = new TestSchedSapUser(this);

    ObjectFactory factory;
    factory.SetTypeId(m_scheduler);
    Ptr<NrMacSchedulerNs3> sched = DynamicCast<NrMacSchedulerNs3>(factory.Create());
    NS_ABORT_MSG_IF(sched == nullptr, "Can't create a NrMacSchedulerNs3 from type " + m_scheduler);

    TestSAPInterface(sched);
    TestAddingRemovingUsersNoData(sched);
    TestUlMcsLimit(sched);
    TestSrBootstrapClassification(sched);
    TestSchedNewData(sched);

    delete m_cSchedSapUser;
    delete m_schedSapUser;
}

class NrTestSchedSuite : public TestSuite
{
  public:
    NrTestSchedSuite()
        : TestSuite("nr-test-sched", Type::SYSTEM)
    {
        AddTestCase(new NrSchedGeneralTestCase("ns3::NrMacSchedulerTdmaRR", "TdmaRR test"),
                    Duration::QUICK);
        AddTestCase(new NrSchedGeneralTestCase("ns3::NrMacSchedulerTdmaPF", "TdmaPF test"),
                    Duration::QUICK);
        AddTestCase(new NrSchedGeneralTestCase("ns3::NrMacSchedulerOfdmaRR", "OfdmaRR test"),
                    Duration::QUICK);
        AddTestCase(new NrSchedGeneralTestCase("ns3::NrMacSchedulerOfdmaPF", "OfdmaPF test"),
                    Duration::QUICK);
    }
};

static NrTestSchedSuite nrSchedTestSuite; //!< Nr scheduler test suite

} // namespace ns3
