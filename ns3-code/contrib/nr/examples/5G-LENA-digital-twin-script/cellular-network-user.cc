/* -*-  Mode: C++; c-file-style: "gnu"; indent-tabs-mode:nil; -*- */

#include <ns3/command-line.h>
#include <ns3/show-progress.h>
#include "cellular-network.h"
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
    cmd.AddValue("numUes",
                "The number of UEs per cell", params.numUes);
    cmd.AddValue("numUesWithVrApp",
                 "The number of UEs that should run the VR/XR application in uplink",
                 params.numUesWithVrApp);
    cmd.AddValue("vrTrafficType",
                 "VR traffic generator to use: trace, synthetic, or none",
                 params.vrTrafficType);
    cmd.AddValue("vrFrameRate",
                 "Frame rate (30 or 60 fps) used by the VR traffic",
                 params.vrFrameRate);
    cmd.AddValue("vrTargetDataRateMbps",
                 "Target data rate in Mbps (used for synthetic VR traffic)",
                 params.vrTargetDataRateMbps);
    cmd.AddValue("vrAppProfile",
                 "Synthetic VR application profile (VirusPopper, Minecraft, GoogleEarthVrCities, GoogleEarthVrTour)",
                 params.vrAppProfile);
    cmd.AddValue ("appGenerationTime",
                "Duration applications will generate traffic.",
                params.appGenerationTime);
    cmd.AddValue ("progressInterval",
                "Progress reporting interval",
                params.progressInterval);
    cmd.AddValue ("randomSeed",
                "Random seed to create repeatable or different runs",
                params.randSeed);
    cmd.AddValue("vrBearerQci",
                 "QCI value (as per NrEpsBearer::Qci) to use for VR traffic bearers",
                 params.vrBearerQci);
    cmd.AddValue("controlBearerQci",
                 "QCI value to use for delay/RTT control bearers",
                 params.controlBearerQci);
    cmd.AddValue("createRemMap",
                 "If true, generate an NR REM coverage map before the simulation starts",
                 params.createRemMap);
    cmd.AddValue("remDirection",
                 "REM direction to generate when createRemMap is true (DL or UL)",
                 params.remDirection);
    // Parse the command line
    cmd.Parse (argc, argv);
    params.ApplyScenarioDefaults();
    params.Validate ();

    std::cout << params;

    ShowProgress spinner (params.progressInterval);

    CellularNetwork (params);

    return 0;
}
