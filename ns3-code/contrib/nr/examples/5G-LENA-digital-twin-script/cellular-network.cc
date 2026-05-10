/* -*-  Mode: C++; c-file-style: "gnu"; indent-tabs-mode:nil; -*- */
/*
 *   Copyright (c) 2020 Centre Tecnologic de Telecomunicacions de Catalunya (CTTC)
 *
 *   This program is free software; you can redistribute it and/or modify
 *   it under the terms of the GNU General Public License version 2 as
 *   published by the Free Software Foundation;
 *
 *   This program is distributed in the hope that it will be useful,
 *   but WITHOUT ANY WARRANTY; without even the implied warranty of
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *   GNU General Public License for more details.
 *
 *   You should have received a copy of the GNU General Public License
 *   along with this program; if not, write to the Free Software
 *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
 *
 */


#include <ns3/nstime.h>
#include <string>
#include <ostream>
#include <cmath>
#include <filesystem>
#include <algorithm>
#include <vector>
#include <array>
// ns3 specific
#include "ns3/antenna-module.h"
#include "ns3/applications-module.h"
#include "ns3/buildings-module.h"
#include "ns3/config-store-module.h"
#include "ns3/config-store.h"
#include "ns3/core-module.h"
#include "ns3/flow-monitor-module.h"
#include "ns3/internet-apps-module.h"
#include "ns3/internet-module.h"
#include "ns3/mobility-module.h"
#include "ns3/network-module.h"
#include "ns3/nr-module.h"
#include "ns3/nr-phy-rx-trace.h"
#include "ns3/nr-radio-environment-map-helper.h"
#include "ns3/point-to-point-module.h"
#include <ns3/radio-environment-map-helper.h>
#include <iomanip>
#include <cctype>
#include "ns3/log.h"
// ns3 VR app
#include "ns3/seq-ts-size-frag-header.h"
#include "ns3/bursty-helper.h"
#include "ns3/burst-sink-helper.h"
#include "ns3/trace-file-burst-generator.h"
#include "ns3/vr-burst-generator.h"
#include "ns3/data-rate.h"

#define CELLULAR_NETWORK_IMPLEMENTATION
#include "cellular-network.h"
#undef CELLULAR_NETWORK_IMPLEMENTATION

NS_LOG_COMPONENT_DEFINE ("CellularNetwork");



namespace ns3 {

namespace {

VrBurstGenerator::VrAppName
GetVrAppNameFromString(const std::string& appName)
{
    std::string normalized;
    normalized.reserve(appName.size());
    for (char c : appName)
    {
        normalized.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    }
    if (normalized == "viruspopper")
    {
        return VrBurstGenerator::VirusPopper;
    }
    if (normalized == "minecraft")
    {
        return VrBurstGenerator::Minecraft;
    }
    if (normalized == "googleearthvrcities" || normalized == "ge_cities")
    {
        return VrBurstGenerator::GoogleEarthVrCities;
    }
    if (normalized == "googleearthvrtour" || normalized == "ge_tour")
    {
        return VrBurstGenerator::GoogleEarthVrTour;
    }
    NS_ABORT_MSG("Unknown synthetic VR app name: " << appName);
}

} // unnamed namespace

    
// Call this function with params containing all the parameters to setup the simulation
void CellularNetwork(const Parameters& params)
{
    
    
    /****************************************************
    *                   Startup things
    *****************************************************/
 
    // Validate the parameter settings  
    params.Validate ();

    // Set random seeds and initialize random stream
    RngSeedManager::SetSeed (params.randSeed+1); 
    RngSeedManager::SetRun (params.randSeed);
    int64_t randomStream = 1;
    
    // Keep a copy for helper routines that still read global parameters
    global_params = params;
    g_rntiToImsi.clear();
    g_rntiToCellId.clear();
    g_cellBwpNumRbPerRbg.clear();
    dlMacStatsStream = nullptr;
    ulMacStatsStream = nullptr;
    srsSinrStream = nullptr;
    ueMacCtrlTxStream = nullptr;
    ueMacStateStream = nullptr;
    ueMacRaTimeoutStream = nullptr;

    // Buffer defaults for RLC and sockets (bytes).
    Config::SetDefault ("ns3::NrRlcUm::MaxTxBufferSize", UintegerValue (params.rlcTxBuffSize)); 
    Config::SetDefault ("ns3::NrRlcUm::ReorderingTimer", TimeValue (MilliSeconds (15)));
    Config::SetDefault ("ns3::NrRlcAm::MaxTxBufferSize", UintegerValue (params.rlcTxBuffSize)); 
    Config::SetDefault ("ns3::TcpSocket::SndBufSize", UintegerValue (params.tcpUdpBuffSize));
    Config::SetDefault ("ns3::TcpSocket::RcvBufSize", UintegerValue (params.tcpUdpBuffSize));
    Config::SetDefault ("ns3::UdpSocket::RcvBufSize", UintegerValue (params.tcpUdpBuffSize));
    
    
    // Create user trace files and write column headers.
    CreateTraceFiles ();

    // Select VR traffic source (trace vs synthetic).
    const bool useTraceVr = (params.vrTrafficType == "trace");
    const bool useSyntheticVr = (params.vrTrafficType == "synthetic");

    std::vector<std::string> vrTraceFiles;
    if (useTraceVr && params.numUesWithVrApp > 0)
    {
        const std::string fpsToken = "_" + std::to_string(params.vrFrameRate) + "fps";
        for (const auto& fileName : params.vrTraceFiles)
        {
            if (fileName.find(fpsToken) != std::string::npos)
            {
                vrTraceFiles.push_back(fileName);
            }
        }
        NS_ABORT_MSG_IF(vrTraceFiles.empty(),
                        "No VR trace files match the requested FPS (" << params.vrFrameRate << ")");
    }
    
    /****************************************************
    * UE and gNodeB creation
    *****************************************************/

    gnbNodes = NodeContainer();
    gnbNodes.Create(1);

    ueNodes = NodeContainer();
    ueNodes.Create(params.numUes);
    g_nodeIdToUeId.clear();
    for (uint32_t ueIdx = 0; ueIdx < ueNodes.GetN(); ++ueIdx)
    {
        g_nodeIdToUeId.emplace(ueNodes.Get(ueIdx)->GetId(), ueIdx);
    }


    /*********************************************************
    * Position Bounding box and Mobility model
    **********************************************************/ 
    
    // gNB is fixed
    Ptr<ListPositionAllocator> gnbPos = CreateObject<ListPositionAllocator>();
    gnbPos->Add(Vector(0.0, 0.0, params.BsHeight));
    MobilityHelper gnbMobility;
    gnbMobility.SetPositionAllocator(gnbPos);
    gnbMobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    gnbMobility.Install(gnbNodes);

    // UE randomness with SteadyStateRandomWaypoint: start uniformly in the same bounding box
    Ptr<RandomBoxPositionAllocator> uePos = CreateObject<RandomBoxPositionAllocator>();
    Ptr<UniformRandomVariable> xPos = CreateObject<UniformRandomVariable>();
    xPos->SetAttribute("Min", DoubleValue(params.boundingBoxMinX));
    xPos->SetAttribute("Max", DoubleValue(params.boundingBoxMaxX));
    uePos->SetAttribute("X", PointerValue(xPos));
    Ptr<UniformRandomVariable> yPos = CreateObject<UniformRandomVariable>();
    yPos->SetAttribute("Min", DoubleValue(params.boundingBoxMinY));
    yPos->SetAttribute("Max", DoubleValue(params.boundingBoxMaxY));
    uePos->SetAttribute("Y", PointerValue(yPos));
    Ptr<ConstantRandomVariable> zPos = CreateObject<ConstantRandomVariable>();
    zPos->SetAttribute("Constant", DoubleValue(1.5));
    uePos->SetAttribute("Z", PointerValue(zPos));
    MobilityHelper ueMobility;
    ueMobility.SetPositionAllocator(uePos);

    // Configure SteadyStateRandomWaypoint defaults (bounding box)
    Config::SetDefault("ns3::SteadyStateRandomWaypointMobilityModel::MinX", DoubleValue(params.boundingBoxMinX));
    Config::SetDefault("ns3::SteadyStateRandomWaypointMobilityModel::MaxX", DoubleValue(params.boundingBoxMaxX));
    Config::SetDefault("ns3::SteadyStateRandomWaypointMobilityModel::MinY", DoubleValue(params.boundingBoxMinY));
    Config::SetDefault("ns3::SteadyStateRandomWaypointMobilityModel::MaxY", DoubleValue(params.boundingBoxMaxY));
    Config::SetDefault("ns3::SteadyStateRandomWaypointMobilityModel::Z", DoubleValue(1.5));

    // Install the model; adjust Min/MaxSpeed as desired
    ueMobility.SetMobilityModel("ns3::SteadyStateRandomWaypointMobilityModel",
                                "MinSpeed", DoubleValue(params.ueMinSpeed),
                                "MaxSpeed", DoubleValue(params.ueMaxSpeed));
    ueMobility.Install(ueNodes);
    
    /***********************************************
    *             5G NR RAN settings
    **********************************************/
    
    // Set some defaults
    Config::SetDefault ("ns3::NrGnbMac::NumberOfRaPreambles", UintegerValue (params.NumberOfRaPreambles));
    Config::SetDefault ("ns3::NrHelper::UseIdealRrc", BooleanValue (params.UseIdealRrc)); // To prevent errors in control channel
    // Use RLC UM for data bearers (DRBs); SRB0 stays TM and SRB1 stays AM in core NR.
    //Config::SetDefault("ns3::NrUeRrc::UseRlcSm", BooleanValue(false));
    //Config::SetDefault("ns3::NrGnbRrc::EpsBearerToRlcMapping",
    //                   EnumValue(NrGnbRrc::RLC_UM_ALWAYS));

     /*
     * Setup the NR module. We create the various helpers needed for the
     * NR simulation:
     * - nrEpcHelper, which will setup the core network
     * - RealisticBeamformingHelper, which takes care of the beamforming part
     * - NrHelper, which takes care of creating and connecting the various
     * part of the NR stack
     * - NrChannelHelper, which takes care of the spectrum channel
     */
    Ptr<NrPointToPointEpcHelper> nrEpcHelper = CreateObject<NrPointToPointEpcHelper>();
    Ptr<RealisticBeamformingHelper> beamformingHelper = CreateObject<RealisticBeamformingHelper>();
    Ptr<NrHelper> nrHelper = CreateObject<NrHelper>();

    // Enable full MIMO CSI feedback (PDSCH, CSI-RS, CSI-IM) so that the PHY reports RI>1 and
    // the scheduler can multiplex multiple spatial layers when the channel allows it.
    /*nrHelper->SetAttribute("CsiFeedbackFlags",
                           UintegerValue(CqiFeedbackFlag::CQI_PDSCH_MIMO |
                                         CqiFeedbackFlag::CQI_CSI_RS |
                                         CqiFeedbackFlag::CQI_CSI_IM));
    // Limit the precoding search to at most 1 layer (rank 1) to keep the configuration consistent
    // with the number of UE antenna rows/columns selected below.
    nrHelper->SetPmSearchAttribute("RankLimit", UintegerValue(2));*/
    nrHelper->SetBeamformingHelper(beamformingHelper);
    nrHelper->SetGnbBeamManagerTypeId(RealisticBfManager::GetTypeId());
    nrHelper->SetGnbBeamManagerAttribute("TriggerEvent",
                                         EnumValue(RealisticBfManager::SRS_COUNT));
    nrHelper->SetUePhyAttribute("EnableUplinkPowerControl",
                                BooleanValue(params.enableUlPc));
    nrHelper->SetSchedulerTypeId(NrMacSchedulerOfdmaPF::GetTypeId());
    nrHelper->SetSchedulerAttribute("EnableBootstrapMcsLimit",
                                    BooleanValue(params.enableBootstrapMcsLimit));
    nrHelper->SetGnbMacAttribute("NumRbPerRbg", UintegerValue(params.numRbPerRbg));
    nrHelper->SetEpcHelper(nrEpcHelper);
    nrHelper->SetUlErrorModel("ns3::NrEesmCcT2");
    nrHelper->SetDlErrorModel("ns3::NrEesmCcT2");

    /*
     * Spectrum division. We create one operational band that contains a single component
     * carrier and a single bandwidth part centered at the frequency specified by the
     * input parameters.
     */
    BandwidthPartInfoPtrVector allBwps;
    CcBwpCreator ccBwpCreator;
    const uint8_t numCcPerBand = 1;

    // Create the configuration for the CcBwpHelper. SimpleOperationBandConf creates a single BWP per CC
    CcBwpCreator::SimpleOperationBandConf bandConf1(params.centralFrequencyBand,
                                                    params.bandwidthHz,
                                                    numCcPerBand);

    OperationBandInfo band = ccBwpCreator.CreateOperationBandContiguousCc(bandConf1);

    /**
     * The channel is configured by this helper using a combination of the scenario, the channel
     * condition model, and the fading model.
     */

    Ptr<NrChannelHelper> channelHelper = CreateObject<NrChannelHelper>();
    channelHelper->ConfigureFactories(params.channelScenario, "Default", "ThreeGpp");
    /**
     * Use channelHelper API to define the attributes for the channel model (condition, pathloss and
     * spectrum)
     */
    // UpdatePeriod controls time-varying channel parameters; condition UpdatePeriod controls LOS/NLOS/O2I changes.
    Config::SetDefault("ns3::ThreeGppChannelModel::UpdatePeriod",
                       TimeValue(params.channelUpdatePeriod));
    channelHelper->SetChannelConditionModelAttribute(
        "UpdatePeriod",
        TimeValue(params.channelConditionUpdatePeriod));
    // Disable log-normal shadowing to reduce channel harshness in this setup.
    channelHelper->SetPathlossAttribute("ShadowingEnabled", BooleanValue(false));
    channelHelper->AssignChannelsToBands({band});
    allBwps = CcBwpCreator::GetAllBwps({band});

    /*
     * allBwps contains all the spectrum configuration needed for the nrHelper.
     *
     * Now, we can setup the attributes. We can have three kind of attributes:
     * (i) parameters that are valid for all the bandwidth parts and applies to
     * all nodes, (ii) parameters that are valid for all the bandwidth parts
     * and applies to some node only, and (iii) parameters that are different for
     * every bandwidth parts. The approach is:
     *
     * - for (i): Configure the attribute through the helper, and then install;
     * - for (ii): Configure the attribute through the helper, and then install
     * for the first set of nodes. Then, change the attribute through the helper,
     * and install again;
     * - for (iii): Install, and then configure the attributes by retrieving
     * the pointer needed, and calling "SetAttribute" on top of such pointer.
     *
     */

    /*
     *  Case (i): Attributes valid for all the nodes
     */
    // Beamforming method for industrial scenario: channel-measurement-driven realistic algorithm
    beamformingHelper->SetBeamformingMethod(RealisticBeamformingAlgorithm::GetTypeId());

    // Core latency
    nrEpcHelper->SetAttribute("S1uLinkDelay", TimeValue(MilliSeconds(0)));

    // Antennas for all the UEs
    nrHelper->SetUeAntennaAttribute("NumRows", UintegerValue(2));
    nrHelper->SetUeAntennaAttribute("NumColumns", UintegerValue(4));
    nrHelper->SetUeAntennaAttribute("AntennaElement",
                                    PointerValue(CreateObject<IsotropicAntennaModel>()));

    // Antennas for all the gNbs
    nrHelper->SetGnbAntennaAttribute("NumRows", UintegerValue(4));
    nrHelper->SetGnbAntennaAttribute("NumColumns", UintegerValue(8));
    nrHelper->SetGnbAntennaAttribute("AntennaElement",
                                     PointerValue(CreateObject<IsotropicAntennaModel>()));

    const uint32_t bwpIdForLowLat = 0;
    const uint32_t bwpIdForRegular = 0;

    // gNb routing between Bearer and bandwidh part
    nrHelper->SetGnbBwpManagerAlgorithmAttribute("NGBR_LOW_LAT_EMBB",
                                                 UintegerValue(bwpIdForLowLat));
    nrHelper->SetGnbBwpManagerAlgorithmAttribute("GBR_CONV_VOICE", UintegerValue(bwpIdForRegular));

    // Ue routing between Bearer and bandwidth part
    nrHelper->SetUeBwpManagerAlgorithmAttribute("NGBR_LOW_LAT_EMBB", UintegerValue(bwpIdForLowLat));
    nrHelper->SetUeBwpManagerAlgorithmAttribute("GBR_CONV_VOICE", UintegerValue(bwpIdForRegular));

    /*
     * We miss many other parameters. By default, not configuring them is equivalent
     * to use the default values. Please, have a look at the documentation to see
     * what are the default values for all the attributes you are not seeing here.
     */

    /*
     * Case (ii): Attributes valid for a subset of the nodes
     */

    // NOT PRESENT IN THIS SIMPLE EXAMPLE

    /*
     * We have configured the attributes we needed. Now, install and get the pointers
     * to the NetDevices, which contains all the NR stack:
     */

    NetDeviceContainer gnbNetDev = nrHelper->InstallGnbDevice(gnbNodes, allBwps);
    NetDeviceContainer ueNetDevs = nrHelper->InstallUeDevice(ueNodes, allBwps);
    InitializeCellBwpNumRbPerRbg(gnbNetDev);
    const uint16_t echoPortNum = 9;
    const uint16_t ulDelayPortNum = 17000;
    const uint16_t dlDelayPortNum = 18000;
    const uint16_t vrPortNum = 16000;
    const uint32_t echoPacketCount = 0xFFFFFFFF;
    NrEpsBearer vrBearer(static_cast<NrEpsBearer::Qci>(params.vrBearerQci));
    Ptr<NrEpcTft> vrTft = Create<NrEpcTft>();
    NrEpcTft::PacketFilter vrPf;
    vrPf.direction = NrEpcTft::UPLINK;
    vrPf.localPortStart = vrPortNum;
    vrPf.localPortEnd = vrPortNum;
    vrTft->Add(vrPf);

    NrEpsBearer ctrlBearer(static_cast<NrEpsBearer::Qci>(params.controlBearerQci));
    Ptr<NrEpcTft> ctrlTft = Create<NrEpcTft>();
    NrEpcTft::PacketFilter dlDelayPf;
    dlDelayPf.direction = NrEpcTft::DOWNLINK;
    dlDelayPf.localPortStart = dlDelayPortNum;
    dlDelayPf.localPortEnd = dlDelayPortNum;
    ctrlTft->Add(dlDelayPf);
    NrEpcTft::PacketFilter ulDelayPf;
    ulDelayPf.direction = NrEpcTft::UPLINK;
    ulDelayPf.remotePortStart = ulDelayPortNum;
    ulDelayPf.remotePortEnd = ulDelayPortNum;
    ctrlTft->Add(ulDelayPf);
    NrEpcTft::PacketFilter rttPf;
    rttPf.direction = NrEpcTft::BIDIRECTIONAL;
    rttPf.remotePortStart = echoPortNum;
    rttPf.remotePortEnd = echoPortNum;
    ctrlTft->Add(rttPf);
    Ptr<NrRadioEnvironmentMapHelper> remHelper;

    randomStream += nrHelper->AssignStreams(gnbNetDev, randomStream);
    randomStream += nrHelper->AssignStreams(ueNetDevs, randomStream);
    /*
     * Case (iii): Go node for node and change the attributes we have to setup
     * per-node.
     */

    // Get the first netdevice (gnbNetDev.Get (0)) and the first bandwidth part (0)
    Ptr<NrGnbPhy> gnbPhy0 = nrHelper->GetGnbPhy(gnbNetDev.Get(0), 0);
    gnbPhy0->SetAttribute("Pattern", StringValue(params.tddPattern));
    gnbPhy0->SetAttribute("Numerology", UintegerValue(params.numerologyBwp1));
    gnbPhy0->SetAttribute("TxPower", DoubleValue(params.BsTxPower));

    // From here, it is standard NS3. In the future, we will create helpers
    // for this part as well.

    /****************************************************
    * Install Internet for all Nodes
    *****************************************************/
    auto [remoteHost, pgwAddress] =
        nrEpcHelper->SetupRemoteHost("100Gb/s", 2500, Seconds(0.000));
    Ptr<Ipv4> remoteHostIpv4 = remoteHost->GetObject<Ipv4>();
    Ipv4Address remoteHostAddr = remoteHostIpv4->GetAddress(1, 0).GetLocal();

    InternetStackHelper internet;
    internet.Install(ueNodes);

    ueIpIfaces = nrEpcHelper->AssignUeIpv4Address(ueNetDevs);

    /****************************************************
    * Attach UEs to gNBs
    *****************************************************/      
    
    nrHelper->AttachToClosestGnb(ueNetDevs, gnbNetDev);

    /***********************************************
    * Traffic generation applications
    **********************************************/

    // Server Config 
    ApplicationContainer serverApps;

    // Declaration of Helpers for Sinks and Servers 
    UdpServerHelper ulDelayPacketSink (ulDelayPortNum);
    UdpServerHelper dlDelayPacketSink (dlDelayPortNum);
    UdpEchoServerHelper echoServer (echoPortNum);
    //vr  
    Ptr<UniformRandomVariable> vrStart = CreateObject<UniformRandomVariable> ();
    vrStart->SetAttribute ("Min", DoubleValue (params.vrStartTimeMin));
    vrStart->SetAttribute ("Max", DoubleValue (params.vrStartTimeMax));
    Ptr<UniformRandomVariable> vrTracePicker = CreateObject<UniformRandomVariable> ();
    vrTracePicker->SetStream (RngSeedManager::GetRun () + 100);
    
    // Server Creation 
    if (params.includeUlDelayApp)
    {
        serverApps.Add (ulDelayPacketSink.Install (remoteHost)); // appId updated on remoteHost
    }
    if (params.includeRttApp)
    {
        serverApps.Add (echoServer.Install (remoteHost)); // appId updated on remoteHost
    }

    //========================================================
    // Client Config 
    ApplicationContainer clientApps;

    // Declarations of Helpers for Clients
    UdpEchoClientHelper echoClient (remoteHostAddr, echoPortNum);
    //vr
    BurstSinkHelper burstSinkHelper ("ns3::UdpSocketFactory",
                                   InetSocketAddress (Ipv4Address::GetAny (), vrPortNum));
    bool vrSinkInstalled = false;
    auto ensureVrSink = [&]() {
        if (!vrSinkInstalled)
        {
            serverApps.Add(burstSinkHelper.Install(remoteHost));
            vrSinkInstalled = true;
        }
    };
    
    // Client Config
    if (params.includeRttApp)
    {
        // Configure echo client application
        echoClient.SetAttribute ("MaxPackets", UintegerValue (echoPacketCount));
        echoClient.SetAttribute ("Interval", TimeValue (params.echoInterPacketInterval));
        echoClient.SetAttribute ("PacketSize", UintegerValue (params.echoPacketSize));
    }
    // VR traffic uses custom helpers configured per UE

    // Client Creation on the desired devices
    Ptr<UniformRandomVariable> startRng = CreateObject<UniformRandomVariable> ();
    startRng->SetStream (RngSeedManager::GetRun ());

    
    const uint32_t totalUes = ueNodes.GetN();
    const uint32_t totalVrUes =
        (useTraceVr || useSyntheticVr)
            ? std::min<uint32_t>(params.numUesWithVrApp, totalUes)
            : 0;
    const uint32_t vrStartIndex = (totalVrUes == 0) ? totalUes : (totalUes - totalVrUes);
    DataRate syntheticVrRate(0);
    VrBurstGenerator::VrAppName syntheticVrApp = VrBurstGenerator::VirusPopper;
    if (useSyntheticVr && totalVrUes > 0)
    {
        syntheticVrRate = DataRate(
            static_cast<uint64_t>(params.vrTargetDataRateMbps * 1e6));
        syntheticVrApp = GetVrAppNameFromString(params.vrAppProfile);
    }

    /***********************************************
    * Iterate through UEs and install apps 
    **********************************************/    
    
    for (uint32_t ueId = 0; ueId < totalUes; ++ueId)
    {
        Ptr<Node> node = ueNodes.Get (ueId);
        Ptr<Ipv4> ipv4 = node->GetObject<Ipv4> ();
        Ipv4InterfaceAddress iaddr = ipv4->GetAddress (1,0); 
        Ipv4Address addr = iaddr.GetLocal ();
        Ptr<NetDevice> ueDevice = ueNetDevs.Get(ueId);

        nrHelper->ActivateDedicatedEpsBearer(ueDevice, ctrlBearer, ctrlTft);
        const bool isTraceVrUe = (useTraceVr && ueId >= vrStartIndex);
        const bool isSyntheticVrUe = (useSyntheticVr && ueId >= vrStartIndex);
        if (isTraceVrUe || isSyntheticVrUe)
        {
            nrHelper->ActivateDedicatedEpsBearer(ueDevice, vrBearer, vrTft);
        }

        // Client apps
        // These are the apps that are on all devices 
        if (params.includeDlDelayApp)
        {
            serverApps.Add (dlDelayPacketSink.Install (node));  
            auto appType3 = InstallDlDelayTrafficApps (node, addr,
                                  remoteHost, dlDelayPortNum, params.appStartTime,
                                  startRng, params.appGenerationTime,
                                  params.delayPacketSize,
                                  params.delayInterval,
                                  params.delayIntervalJitter);
            clientApps.Add (appType3.first);
        }
        if (params.includeUlDelayApp)
        {
            auto appType2 = InstallUlDelayTrafficApps (node,
                                  remoteHost, remoteHostAddr, ulDelayPortNum, params.appStartTime,
                                  startRng, params.appGenerationTime,
                                  params.delayPacketSize,
                                  params.delayInterval,
                                  params.delayIntervalJitter);
            clientApps.Add (appType2.first);
        }
        if (params.includeRttApp)
        {
            auto appType1 = InstallUdpEchoApps (node,
                              &echoClient,
                              params.appStartTime,
                              startRng, params.appGenerationTime);
            clientApps.Add (appType1.first);
            for (auto app = appType1.first.Begin(); app != appType1.first.End(); ++app)
            {
                Ptr<UdpEchoClient> echo = DynamicCast<UdpEchoClient>(*app);
                if (echo != nullptr)
                {
                    echo->TraceConnectWithoutContext(
                        "TxWithAddresses",
                        MakeBoundCallback(&StampEchoClientPacket, ueId));
                }
            }
        } 
        if (isTraceVrUe) 
        {
            // Random sample for the start time fo the VR session for each UE  
            double vrStartTime = vrStart->GetValue();
            // The sender of VR traffic to be installed on remoteHost
            const uint32_t traceIdx =
                vrTracePicker->GetInteger(0, static_cast<int>(vrTraceFiles.size()) - 1);
            const std::string& vrTraceFile = vrTraceFiles[traceIdx];
            BurstyHelper burstyHelper ("ns3::UdpSocketFactory", 
                                       InetSocketAddress (remoteHostAddr, vrPortNum)); 
            burstyHelper.SetAttribute ("FragmentSize", UintegerValue (1200));
            burstyHelper.SetBurstGenerator ("ns3::TraceFileBurstGenerator", 
                                            "TraceFile", StringValue (params.traceFolder + vrTraceFile), 
                                            "StartTime", DoubleValue (vrStartTime));
            serverApps.Add (burstyHelper.Install (node));
            ensureVrSink();
            std::cout << " VR trace file " << vrTraceFile << " scheduled at t="
                      << vrStartTime << "s for UE IMSI " << GetImsi_from_node(node) << std::endl;
            // Print the IMSI of the ues that are doing this	
            std::cout << " IMSI: " << GetImsi_from_node(node) 
                << " Ip_addr: " << addr 
                << " has VR app installed " << std::endl;
            continue;
        }
        if (isSyntheticVrUe)
        {
            double vrStartTime = vrStart->GetValue();
            BurstyHelper burstyHelper("ns3::UdpSocketFactory",
                                      InetSocketAddress(remoteHostAddr, vrPortNum));
            burstyHelper.SetAttribute("FragmentSize", UintegerValue(1200));
            burstyHelper.SetBurstGenerator("ns3::VrBurstGenerator",
                                           "FrameRate", DoubleValue(params.vrFrameRate),
                                           "TargetDataRate", DataRateValue(syntheticVrRate),
                                           "VrAppName", EnumValue(syntheticVrApp));
            serverApps.Add(burstyHelper.Install(node));
            ensureVrSink();
            std::cout << " Synthetic VR app (" << params.vrAppProfile
                      << ") scheduled at t=" << vrStartTime << "s for UE IMSI "
                      << GetImsi_from_node(node) << std::endl;
            continue;
        }
    } // end of for over UEs


    
    // Server Start  
    serverApps.Start (params.appStartTime);
    // client apps are started individually using the Install function 

    // enable the RAN traces provided by the NR module
    // Custom selection of NR helper traces (mirrors EnableTraces()).
    // WARNING: If EnableDlDataPhyTraces/EnableDlCtrlPhyTraces/EnableUlPhyTraces,
    // EnablePdcpSimpleTraces, or EnableRlcSimpleTraces is enabled, internal logging
    // will take over.
    SetupNrTraces(gnbNetDev, nrHelper);

    // enable packet tracing from the application layer 
    // appId is being used here BE CAREFUL about changing the order 
    // in which the apps get added to the server container
    if (params.includeUlDelayApp || params.includeDlDelayApp)
    {
        Config::Connect ("/NodeList/*/ApplicationList/*/$ns3::UdpServer/RxWithAddresses", 
        MakeBoundCallback (&udpServerTrace, 
                           std::make_pair(ulDelayPortNum, dlDelayPortNum),
                           remoteHost));
    }

    // connect custom trace sinks for RRC connection establishment and handover notification
    
    Config::Connect ("/NodeList/*/DeviceList/*/NrUeRrc/ConnectionEstablished",
                   MakeCallback (&NotifyConnectionEstablishedUe));
    Config::Connect ("/NodeList/*/DeviceList/*/NrGnbRrc/ConnectionEstablished",
                   MakeCallback (&NotifyConnectionEstablishedEnb));
    // Connect PDCP/RLC traces after bearer reconfiguration to avoid missing maps at time 0.
    Config::Connect ("/NodeList/*/DeviceList/*/NrUeRrc/ConnectionReconfiguration",
                   MakeCallback (&ConnectPdcpRlcTracesUe));
    Config::Connect ("/NodeList/*/DeviceList/*/NrGnbRrc/ConnectionReconfiguration",
                   MakeCallback (&ConnectPdcpRlcTracesGnb));
    if (params.includeRttApp)
    {
        Config::Connect ("/NodeList/*/ApplicationList/*/$ns3::UdpEchoClient/RxWithAddresses", 
                         MakeBoundCallback (&rttTrace, rttStream));
    }
    if (useTraceVr || useSyntheticVr)
    {
        Config::Connect ("/NodeList/*/ApplicationList/*/$ns3::BurstSink/BurstRx", 
                         MakeBoundCallback (&BurstRx, burstRxStream));
        Config::Connect ("/NodeList/*/ApplicationList/*/$ns3::BurstSink/FragmentRx", 
                         MakeBoundCallback (&FragmentRx, fragmentRxStream));
    }

    if (params.createRemMap)
    {
        NS_ABORT_MSG_IF(gnbNetDev.GetN() == 0 || ueNetDevs.GetN() == 0,
                        "Cannot create REM without gNB and UE devices");
        std::string remDir = params.remDirection;
        std::transform(remDir.begin(), remDir.end(), remDir.begin(),
                       [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
        remHelper = CreateObject<NrRadioEnvironmentMapHelper>();
        remHelper->SetRemMode(NrRadioEnvironmentMapHelper::COVERAGE_AREA);
        remHelper->SetMinX(params.boundingBoxMinX);
        remHelper->SetMaxX(params.boundingBoxMaxX);
        remHelper->SetMinY(params.boundingBoxMinY);
        remHelper->SetMaxY(params.boundingBoxMaxY);
        remHelper->SetResX(100);
        remHelper->SetResY(100);
        remHelper->SetZ(params.ueHeight);
        if (remDir == "dl")
        {
            remHelper->CreateRem(gnbNetDev, ueNetDevs.Get(0), 0);
        }
        else if (remDir == "ul")
        {
            Vector gnbPos =
                gnbNodes.Get(0)->GetObject<MobilityModel>()->GetPosition();
            std::array<Vector, 4> corners = {
                Vector(params.boundingBoxMinX, params.boundingBoxMinY, params.ueHeight),
                Vector(params.boundingBoxMinX, params.boundingBoxMaxY, params.ueHeight),
                Vector(params.boundingBoxMaxX, params.boundingBoxMinY, params.ueHeight),
                Vector(params.boundingBoxMaxX, params.boundingBoxMaxY, params.ueHeight)};
            Vector farthest = corners[0];
            double maxDistSq = 0.0;
            for (const auto& corner : corners)
            {
                double dx = corner.x - gnbPos.x;
                double dy = corner.y - gnbPos.y;
                double dz = corner.z - gnbPos.z;
                double distSq = dx * dx + dy * dy + dz * dz;
                if (distSq > maxDistSq)
                {
                    maxDistSq = distSq;
                    farthest = corner;
                }
            }
            ueNodes.Get(0)->GetObject<MobilityModel>()->SetPosition(farthest);
            NetDeviceContainer remUeDevs;
            remUeDevs.Add(ueNetDevs.Get(0));
            remHelper->CreateRem(remUeDevs, gnbNetDev.Get(0), 0);
        }
        else
        {
            NS_ABORT_MSG("Unknown remDirection: " << params.remDirection);
        }
    }

    // Add some extra time for the last generated packets to be received
    PrintSimInfoToFile ();
    const Time appStopWindow = MilliSeconds (50);
    Time stopTime = params.appStartTime + appStartWindow + params.appGenerationTime + appStopWindow;
    std::cout << "\n------------------------------------------------------\n";
    std::cout << "Start Simulation ! Runtime: " << stopTime.GetSeconds() << " seconds\n";
    Simulator::Stop (stopTime);
    // schedule the periodic logging of UE positions
    Simulator::Schedule (MilliSeconds(500), &LogPosition, mobStream);
    Simulator::Run ();
    std::cout << "\n------------------------------------------------------\n"
            << "End simulation"
            << std::endl;
    Simulator::Destroy ();
}// end of Cellural-network
    

} // end of namespace ns3
