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
#include <sstream>
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

#define DELAY_BENCHMARKING_IMPLEMENTATION
#include "delay-benchmarking.h"
#undef DELAY_BENCHMARKING_IMPLEMENTATION

NS_LOG_COMPONENT_DEFINE ("CellularNetwork");



namespace ns3 {

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

    // Set buffer sizes
    Config::SetDefault ("ns3::NrRlcUm::MaxTxBufferSize", UintegerValue (params.rlcTxBuffSize)); 
    Config::SetDefault ("ns3::NrRlcUm::ReorderingTimer", TimeValue (MilliSeconds (15)));
    Config::SetDefault ("ns3::NrRlcAm::MaxTxBufferSize", UintegerValue (params.rlcTxBuffSize)); 
    Config::SetDefault ("ns3::TcpSocket::SndBufSize", UintegerValue (params.tcpUdpBuffSize));
    Config::SetDefault ("ns3::TcpSocket::RcvBufSize", UintegerValue (params.tcpUdpBuffSize));
    Config::SetDefault ("ns3::UdpSocket::RcvBufSize", UintegerValue (params.tcpUdpBuffSize));
    
    
    // Create user created trace files with corresponding column names
    CreateTraceFiles ();

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

    // UE fixed positions, stationary
    Ptr<ListPositionAllocator> uePos = CreateObject<ListPositionAllocator>();
    for (uint32_t ueIdx = 0; ueIdx < ueNodes.GetN(); ++ueIdx)
    {
        uePos->Add(Vector(params.uePosX, params.uePosY, params.ueHeight));
    }
    MobilityHelper ueMobility;
    ueMobility.SetPositionAllocator(uePos);
    ueMobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
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
    if (params.fixUlMcs == 0)
    {
        // Keep default adaptive UL MCS selection based on channel quality.
        nrHelper->SetSchedulerAttribute("FixedMcsUl", BooleanValue(false));
    }
    else
    {
        nrHelper->SetSchedulerAttribute("FixedMcsUl", BooleanValue(true));
        nrHelper->SetSchedulerAttribute("StartingMcsUl", UintegerValue(params.fixUlMcs));
    }
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
    const uint16_t ulDelayPortNum = 17000;
    const uint16_t dlDelayPortNum = 18000;
    const uint16_t ulLoadPortNum = 19000;
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
    const bool hasLoad = (params.loadType != "none");
    const bool loadTcp = (params.loadType == "tcp");
    if (hasLoad)
    {
        NrEpcTft::PacketFilter ulLoadPf;
        ulLoadPf.remotePortStart = ulLoadPortNum;
        ulLoadPf.remotePortEnd = ulLoadPortNum;
        ctrlTft->Add(ulLoadPf);
    }

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
    PacketSinkHelper ulLoadTcpSink ("ns3::TcpSocketFactory",
                                    InetSocketAddress (Ipv4Address::GetAny (), ulLoadPortNum));
    PacketSinkHelper ulLoadUdpSink ("ns3::UdpSocketFactory",
                                    InetSocketAddress (Ipv4Address::GetAny (), ulLoadPortNum));
    
    // Server Creation 
    if (params.includeUlDelayApp)
    {
        serverApps.Add (ulDelayPacketSink.Install (remoteHost)); // appId updated on remoteHost
    }
    if (hasLoad)
    {
        if (loadTcp)
        {
            serverApps.Add (ulLoadTcpSink.Install (remoteHost));
        }
        else
        {
            serverApps.Add (ulLoadUdpSink.Install (remoteHost));
        }
    }

    //========================================================
    // Client Config 
    ApplicationContainer clientApps;

    // Delay traffic uses a jittered UDP client configured per UE.

    // Client Creation on the desired devices
    Ptr<UniformRandomVariable> startRng = CreateObject<UniformRandomVariable> ();
    startRng->SetStream (RngSeedManager::GetRun ());

    
    const uint32_t totalUes = ueNodes.GetN();

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

        // Client apps
        // These are the apps that are on all devices 
        if (params.includeDlDelayApp)
        {
            serverApps.Add (dlDelayPacketSink.Install (node));  
            auto appType3 = InstallDlDelayTrafficApps (node, addr,
                                  remoteHost, dlDelayPortNum, params.appStartTime,
                                  startRng, params.appGenerationTime,
                                  params.delayPacketSize, params.delayInterval,
                                  params.delayIntervalJitter);
            clientApps.Add (appType3.first);
        }
        if (params.includeUlDelayApp)
        {
            auto appType2 = InstallUlDelayTrafficApps (node,
                                  remoteHostAddr, ulDelayPortNum, params.appStartTime,
                                  startRng, params.appGenerationTime,
                                  params.delayPacketSize, params.delayInterval,
                                  params.delayIntervalJitter);
            clientApps.Add (appType2.first);
        }
        if (hasLoad && ueId == 1)
        {
            double loadStartMs = startRng->GetValue (params.appStartTime.GetMilliSeconds (),
                                                     (params.appStartTime + appStartWindow).GetMilliSeconds ());
            Time loadStartTime = MilliSeconds (loadStartMs);
            if (loadTcp)
            {
                BulkSendHelper bulk ("ns3::TcpSocketFactory",
                                     InetSocketAddress (remoteHostAddr, ulLoadPortNum));
                bulk.SetAttribute ("MaxBytes", UintegerValue (0));
                ApplicationContainer loadApp = bulk.Install (node);
                loadApp.Start (loadStartTime);
                loadApp.Stop (loadStartTime + params.appGenerationTime);
                clientApps.Add (loadApp);
            }
            else
            {
                OnOffHelper onoff ("ns3::UdpSocketFactory",
                                   InetSocketAddress (remoteHostAddr, ulLoadPortNum));
                onoff.SetAttribute ("DataRate",
                                    DataRateValue (DataRate (static_cast<uint64_t>(params.cbrLoadMbps * 1e6))));
                onoff.SetAttribute ("PacketSize", UintegerValue (1400));
                onoff.SetAttribute ("OnTime",
                                    StringValue ("ns3::ConstantRandomVariable[Constant=1]"));
                onoff.SetAttribute ("OffTime",
                                    StringValue ("ns3::ConstantRandomVariable[Constant=0]"));
                ApplicationContainer loadApp = onoff.Install (node);
                loadApp.Start (loadStartTime);
                loadApp.Stop (loadStartTime + params.appGenerationTime);
                clientApps.Add (loadApp);
            }
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
    if (hasLoad)
    {
        std::ostringstream loadPath;
        loadPath << "/NodeList/" << remoteHost->GetId()
                 << "/ApplicationList/*/$ns3::PacketSink/RxWithAddresses";
        const std::string proto = loadTcp ? "TCP" : "UDP";
        Config::Connect (loadPath.str(),
                         MakeBoundCallback(&loadTrace, loadTraceStream, proto));
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
    // Add some extra time for the last generated packets to be received
    PrintSimInfoToFile ();
    const Time appStopWindow = MilliSeconds (50);
    Time stopTime = params.appStartTime + appStartWindow + params.appGenerationTime + appStopWindow;
    std::cout << "\n------------------------------------------------------\n";
    std::cout << "Start Simulation ! Runtime: " << stopTime.GetSeconds() << " seconds\n";
    Simulator::Stop (stopTime);
    Simulator::Run ();
    std::cout << "\n------------------------------------------------------\n"
            << "End simulation"
            << std::endl;
    Simulator::Destroy ();
}// end of Cellural-network
    

} // end of namespace ns3
