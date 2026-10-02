/* -*-  Mode: C++; c-file-style: "gnu"; indent-tabs-mode:nil; -*- */

#include <ns3/command-line.h>
#include <ns3/show-progress.h>
#include <algorithm>
#include <cctype>
#include <cstdint>
#include <limits>
#include "delay-benchmarking.h"
/*
 * QCI lookup (NrEpsBearer::Qci):
 *  1  -> GBR_CONV_VOICE              67 -> GBR_MC_VIDEO
 *  2  -> GBR_CONV_VIDEO              69 -> NGBR_MC_DELAY_SIGNAL
 *  3  -> GBR_GAMING                  70 -> NGBR_MC_DATA
 *  4  -> GBR_NON_CONV_VIDEO          71 -> GBR_LIVE_UL_71
 *  5  -> NGBR_IMS                    72 -> GBR_LIVE_UL_72
 *  6  -> NGBR_VIDEO_TCP_OPERATOR     73 -> GBR_LIVE_UL_73
 *  7  -> NGBR_VOICE_VIDEO_GAMING     74 -> GBR_LIVE_UL_74
 *  8  -> NGBR_VIDEO_TCP_PREMIUM      75 -> GBR_V2X
 *  9  -> NGBR_VIDEO_TCP_DEFAULT      76 -> GBR_LIVE_UL_76
 * 65  -> GBR_MC_PUSH_TO_TALK         79 -> NGBR_V2X
 * 66  -> GBR_NMC_PUSH_TO_TALK        80 -> NGBR_LOW_LAT_EMBB
 * 82  -> DGBR_DISCRETE_AUT_SMALL     83 -> DGBR_DISCRETE_AUT_LARGE
 * 84  -> DGBR_ITS                    85 -> DGBR_ELECTRICITY
 * 86  -> DGBR_V2X                    87 -> DGBR_INTER_SERV_87
 * 88  -> DGBR_INTER_SERV_88          89 -> DGBR_VISUAL_CONTENT_89
 * 90  -> DGBR_VISUAL_CONTENT_90
 */
using namespace ns3;


int
main (int argc, char *argv[])
{
    Parameters params;
    std::string tddPatternOverride;
    int64_t srPeriodicitySlotsOverride = -1;
    int64_t srOffsetSlotsOverride = -1;
    int64_t numRbPerRbgOverride = -1;
    int64_t bootstrapGrantPrbsOverride = -1;
    int64_t bootstrapMaxMcsOverride = -1;
    int64_t numerologyOverride = -1;
    /*
    * From here, we instruct the ns3::CommandLine class of all the input parameters
    * that we may accept as input, as well as their description, and the storage
    * variable.
    */
    CommandLine cmd;

    cmd.AddValue("digitalTwinScenario",
                 "Digital twin preset to use (expeca or 5gsmart)",
                 params.digitalTwinScenario);
    cmd.AddValue("channelScenario",
                 "NR channel scenario (e.g., InH-OfficeMixed, InH-OfficeOpen, UMa, InF)",
                 params.channelScenario);
    cmd.AddValue("uePosX",
                 "UE X position (meters) for delay benchmarking",
                 params.uePosX);
    cmd.AddValue("uePosY",
                 "UE Y position (meters) for delay benchmarking",
                 params.uePosY);
    cmd.AddValue("direction",
                 "Delay probe direction: ul, dl, or both",
                 params.direction);
    cmd.AddValue("loadType",
                 "Background load type: none, udp, or tcp",
                 params.loadType);
    cmd.AddValue("numBackgroundUes",
                 "Number of background-traffic UEs; ignored when loadType is none",
                 params.numBackgroundUes);
    cmd.AddValue("totalBackgroundLoad",
                 "Aggregate UDP CBR background load in Mbps; divided equally across background UEs",
                 params.totalBackgroundLoadMbps);
    cmd.AddValue("delayTrafficSource",
                 "Probe traffic source: delay or burst",
                 params.delayTrafficSource);
    cmd.AddValue("delayPktSize",
                 "Total UDP payload size per packet, including the source's measurement header",
                 params.delayPktSize);
    cmd.AddValue("delayInterval",
                 "Mean interval between one-packet probe events or multi-packet burst events",
                 params.delayInterval);
    cmd.AddValue("delayBurstPackets",
                 "Number of UDP packets generated together in each burst",
                 params.delayBurstPackets);
    cmd.AddValue ("appGenerationTime",
                "Duration applications will generate traffic.",
                params.appGenerationTime);
    cmd.AddValue ("progressInterval",
                "Progress reporting interval",
                params.progressInterval);
    cmd.AddValue ("randomSeed",
                "Random seed to create repeatable or different runs",
                params.randSeed);
    cmd.AddValue("controlBearerQci",
                 "QCI value to use for delay/RTT control bearers",
                 params.controlBearerQci);
    cmd.AddValue("fixUlMcs",
                 "UL MCS control: 0 keeps adaptive AMC; 1..27 forces fixed UL MCS",
                 params.fixUlMcs);
    cmd.AddValue("tddPattern",
                 "TDD slot pattern, using DL, UL, F, or S tokens separated by |",
                 tddPatternOverride);
    cmd.AddValue("srPeriodicitySlots",
                 "Scheduling-request opportunity period in slots; zero means every slot, -1 uses profile default",
                 srPeriodicitySlotsOverride);
    cmd.AddValue("srOffsetSlots",
                 "Scheduling-request opportunity offset in slots; -1 uses profile default",
                 srOffsetSlotsOverride);
    cmd.AddValue("numRbPerRbg",
                 "Number of physical resource blocks per resource-block group; -1 uses profile default",
                 numRbPerRbgOverride);
    cmd.AddValue("bootstrapGrantPrbs",
                 "Minimum SR bootstrap UL grant size in physical resource blocks; -1 uses profile default",
                 bootstrapGrantPrbsOverride);
    cmd.AddValue("bootstrapMaxMcs",
                 "Maximum MCS used by an SR bootstrap UL grant; -1 uses profile default",
                 bootstrapMaxMcsOverride);
    cmd.AddValue("numerology",
                 "NR numerology (0..5); SCS is 15 * 2^numerology kHz; -1 uses profile default",
                 numerologyOverride);
    // Parse user input first to select the profile, then apply explicit radio overrides below.
    cmd.Parse (argc, argv);
    params.ApplyScenarioDefaults();

    auto applyUintOverride = [](const char* name, int64_t overrideValue, uint32_t& value) {
        if (overrideValue == -1)
        {
            return;
        }
        NS_ABORT_MSG_IF(
            overrideValue < 0 ||
                static_cast<uint64_t>(overrideValue) > std::numeric_limits<uint32_t>::max(),
            name << " must fit in an unsigned 32-bit integer");
        value = static_cast<uint32_t>(overrideValue);
    };
    if (!tddPatternOverride.empty())
    {
        params.tddPattern = tddPatternOverride;
    }
    applyUintOverride("srPeriodicitySlots",
                      srPeriodicitySlotsOverride,
                      params.srPeriodicitySlots);
    applyUintOverride("srOffsetSlots", srOffsetSlotsOverride, params.srOffsetSlots);
    applyUintOverride("numRbPerRbg", numRbPerRbgOverride, params.numRbPerRbg);
    applyUintOverride("bootstrapGrantPrbs",
                      bootstrapGrantPrbsOverride,
                      params.bootstrapGrantPrbs);
    applyUintOverride("bootstrapMaxMcs", bootstrapMaxMcsOverride, params.bootstrapMaxMcs);
    if (numerologyOverride != -1)
    {
        NS_ABORT_MSG_IF(numerologyOverride < 0 || numerologyOverride > 5,
                        "numerology must be in [0,5]");
        params.numerologyBwp1 = static_cast<uint16_t>(numerologyOverride);
    }
    std::string load = params.loadType;
    std::transform(load.begin(), load.end(), load.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    params.loadType = load;
    std::transform(params.delayTrafficSource.begin(), params.delayTrafficSource.end(),
                   params.delayTrafficSource.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    params.numUes = (load != "none") ? 1 + params.numBackgroundUes : 1;
    std::string dir = params.direction;
    std::transform(dir.begin(), dir.end(), dir.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    if (dir == "ul")
    {
        params.includeUlDelayApp = true;
        params.includeDlDelayApp = false;
    }
    else if (dir == "dl")
    {
        params.includeUlDelayApp = false;
        params.includeDlDelayApp = true;
    }
    else if (dir == "both")
    {
        params.includeUlDelayApp = true;
        params.includeDlDelayApp = true;
    }
    if (params.delayTrafficSource == "burst")
    {
        params.includeUlDelayApp = false;
        params.includeDlDelayApp = false;
    }
    params.Validate ();

    std::cout << params;

    ShowProgress spinner (params.progressInterval);

    CellularNetwork (params);

    return 0;
}
