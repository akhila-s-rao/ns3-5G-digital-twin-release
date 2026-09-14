#ifndef DIGITAL_TWIN_RADIO_PROFILE_H
#define DIGITAL_TWIN_RADIO_PROFILE_H

#include <cstdint>
#include <string>

namespace ns3
{

struct CommonRadioParameters
{
    uint16_t numerologyBwp1 = 1;
    double centralFrequencyBand = 3.5e9;
    double bandwidthHz = 40e6;
    std::string tddPattern =
        "DL|DL|DL|F|UL|DL|DL|DL|F|UL|DL|DL|DL|F|UL|DL|DL|DL|F|UL";
    uint32_t fSlotDlAllocationSymbols = 5;
    uint32_t fSlotUlAllocationSymbols = 3;
    bool enableSrsInFSlots = false;
    bool enableSrsInUlSlots = true;
    uint32_t srsPeriodicityUlOpportunities = 16;
    uint32_t ueAntennaRows = 1;
    uint32_t ueAntennaColumns = 1;
    uint32_t gnbAntennaRows = 1;
    uint32_t gnbAntennaColumns = 1;
    int16_t poNominalPusch = -96;
    double ueNoiseFigureDb = 5.0;
    double gnbNoiseFigureDb = 5.0;
    uint32_t numRbPerRbg = 1;
    uint32_t n2DelaySlots = 6;
    uint32_t ulSchedulerLookaheadSlots = 6;
    uint32_t ueL1L2CtrlLatencySlots = 0;
    uint32_t gnbL1L2CtrlLatencySlots = 2;
    uint32_t gnbTbDecodeLatencyUs = 0;
    uint32_t srPeriodicitySlots = 10;
    uint32_t srOffsetSlots = 3;
    uint32_t maxUlMcs = 20;
    uint32_t rlcTxBuffSize = 80 * 1024;
    uint32_t tcpUdpBuffSize = 500 * 1024;
};

inline void
ApplyExpecaRadioProfile(CommonRadioParameters& params)
{
    params = CommonRadioParameters{};
}

} // namespace ns3

#endif // DIGITAL_TWIN_RADIO_PROFILE_H
