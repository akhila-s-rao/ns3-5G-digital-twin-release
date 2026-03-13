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
#include <cstdint>
#include <ostream>
#include <vector>
#include <unordered_map>
#include <unordered_set>
#include <memory>
#include <algorithm>
#include <cctype>
#include <cmath>
#include <sstream>
#include "ns3/core-module.h"
#include "ns3/config-store.h"
#include "ns3/config.h"
#include "ns3/network-module.h"
#include "ns3/internet-module.h"
#include "ns3/internet-apps-module.h"
#include "ns3/applications-module.h"
#include "ns3/mobility-module.h"
#include "ns3/antenna-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/lte-module.h"
#include <ns3/radio-environment-map-helper.h>
#include "ns3/config-store-module.h"
#include "ns3/inet-socket-address.h"
#include "ns3/nr-ue-net-device.h"
#include "ns3/nr-gnb-net-device.h"
#include "ns3/nr-gnb-mac.h"
#include "ns3/nr-gnb-phy.h"
#include "ns3/nr-gnb-rrc.h"
#include "ns3/nr-ue-rrc.h"
#include "ns3/nr-ue-mac.h"
#include "ns3/nr-eps-bearer.h"
#include "ns3/nr-spectrum-phy.h"
#include <iomanip>
#include "ns3/log.h"
#include "ns3/nr-phy-mac-common.h"
#include "ns3/nr-control-messages.h"
#include "ns3/nr-common.h"
#include "ns3/nr-mac-short-bsr-ce.h"
#include "nr-trace-streams.h"

#ifndef DELAY_BENCHMARKING_FUNCTION_H
#define DELAY_BENCHMARKING_FUNCTION_H

    // NrEpsBearer::Qci (Release 18) values, priority ranks (lower is higher priority),
    // and packet delay budget (PDB) in ms:
    // +-----------------------------+-----+----------+----------+
    // | Bearer (NrEpsBearer::Qci)   | QCI | Priority | PDB (ms) |
    // +-----------------------------+-----+----------+----------+
    // | GBR_CONV_VOICE              | 1   | 20       | 100      |
    // | GBR_CONV_VIDEO              | 2   | 40       | 150      |
    // | GBR_GAMING                  | 3   | 30       | 50       |
    // | GBR_NON_CONV_VIDEO          | 4   | 50       | 300      |
    // | NGBR_IMS                    | 5   | 10       | 100      |
    // | NGBR_VIDEO_TCP_OPERATOR     | 6   | 60       | 300      |
    // | NGBR_VOICE_VIDEO_GAMING     | 7   | 70       | 100      |
    // | NGBR_VIDEO_TCP_PREMIUM      | 8   | 80       | 300      |
    // | NGBR_VIDEO_TCP_DEFAULT      | 9   | 90       | 300      |
    // | GBR_MC_PUSH_TO_TALK         | 65  | 7        | 75       |
    // | GBR_NMC_PUSH_TO_TALK        | 66  | 20       | 100      |
    // | GBR_MC_VIDEO                | 67  | 15       | 100      |
    // | NGBR_MC_DELAY_SIGNAL        | 69  | 5        | 60       |
    // | NGBR_MC_DATA                | 70  | 55       | 200      |
    // | GBR_LIVE_UL_71              | 71  | 56       | 150      |
    // | GBR_LIVE_UL_72              | 72  | 56       | 300      |
    // | GBR_LIVE_UL_73              | 73  | 56       | 300      |
    // | GBR_LIVE_UL_74              | 74  | 56       | 500      |
    // | GBR_V2X                     | 75  | 25       | 50       |
    // | GBR_LIVE_UL_76              | 76  | 56       | 500      |
    // | NGBR_V2X                    | 79  | 65       | 5        |
    // | NGBR_LOW_LAT_EMBB           | 80  | 68       | 10       |
    // | DGBR_DISCRETE_AUT_SMALL     | 82  | 19       | 10       |
    // | DGBR_DISCRETE_AUT_LARGE     | 83  | 22       | 10       |
    // | DGBR_ITS                    | 84  | 24       | 30       |
    // | DGBR_ELECTRICITY            | 85  | 21       | 5        |
    // | DGBR_V2X                    | 86  | 18       | 5        |
    // | DGBR_INTER_SERV_87          | 87  | 25       | 5        |
    // | DGBR_INTER_SERV_88          | 88  | 25       | 10       |
    // | DGBR_VISUAL_CONTENT_89      | 89  | 25       | 15       |
    // | DGBR_VISUAL_CONTENT_90      | 90  | 25       | 20       |
    // +-----------------------------+-----+----------+----------+
    
namespace ns3 {

class NrHelper;

// Contains all parameters we are setting. Command line user settable parameters are included in cellular-netwokr-user.cc
// The rest are still set here but not user settable. 
struct Parameters
{
    friend std::ostream& operator<< (std::ostream& os, const Parameters& parameters);

    std::string ns3Dir = "/home/ubuntu/ns-3-dev/";
    std::string digitalTwinScenario = "expeca";

    // Deployment topology parameters
    uint16_t numUes = 3;
    // num of gNodeBs is set at 1 for now
    double BsHeight = 10;
    double ueHeight = 1.5;
    std::string loadType = "none"; // none, udp, or tcp

    // Simulation parameters
    Time appGenerationTime = Seconds (5);
    Time appStartTime = MilliSeconds (500);
    Time progressInterval = Seconds (1);
    uint32_t randSeed = 13;

    // NR RAN parameters (Reference: 3GPP TR 38.901 V17.0.0 (Release 17)
    // Table 7.8-1 for the power and BW).
    // This example uses a single operational band/BWP
    uint16_t numerologyBwp1 = 1;
    std::string channelScenario = "InH-OfficeOpen"; // "InH-OfficeMixed", "InH-OfficeOpen", "UMa"
    // Channel update period: forces regeneration of channel parameters over time (time-varying fading).
    Time channelUpdatePeriod = MilliSeconds(20);
    // Channel condition update period: recomputes LOS/NLOS (and O2I if enabled) over time.
    Time channelConditionUpdatePeriod = Seconds(10);
    double centralFrequencyBand = 3.5e9;
    double bandwidthHz = 40e6;
    // the pattern length needs to be as long as the number of slots in a 10 ms frame
    // So adjust according to your numerology 
    std::string tddPattern
        = "DL|DL|DL|S|UL|DL|DL|DL|S|UL|DL|DL|DL|S|UL|DL|DL|DL|S|UL";
    uint16_t BsTxPower = 20;
    bool enableUlPc = true;
    uint16_t NumberOfRaPreambles = 40;
    bool UseIdealRrc = true;
    uint32_t numRbPerRbg = 5; // NR scheduler RBG size in RBs.
    
    // Buffer sizes 
    uint32_t rlcTxBuffSize = 200 * 1024; // default is 10240 
    uint32_t tcpUdpBuffSize = 500 * 1024; // default is 131072

    // position and mobility model
    double boundingBoxMinX = -45.0;
    double boundingBoxMaxX = 45.0;
    double boundingBoxMinY = -45.0;
    double boundingBoxMaxY = 45.0;
    double uePosX = 5.0;
    double uePosY = 0.0;
    double ueMinSpeed = 0.5;
    double ueMaxSpeed = 1.5;

    // Application traffic parameters
    // OWD = one-way delay
    bool includeUlDelayApp = true;
    bool includeDlDelayApp = true;
    std::string direction = "ul"; // ul, dl, or both
    double cbrLoadMbps = 10.0;
    uint8_t controlBearerQci = NrEpsBearer::NGBR_LOW_LAT_EMBB; // NGBR_LOW_LAT_EMBB= priority_rank 68, NGBR_IMS=10
    // UL MCS control: 0 keeps adaptive UL AMC; 1..27 fixes UL MCS to this value.
    uint32_t fixUlMcs = 0;
    bool enableBootstrapMcsLimit = true; // Cap SR bootstrap UL grant MCS to min(estimated, 9).

    // UDP one way delay probes
    uint32_t delayPacketSize = 1400;
    Time delayInterval = Seconds (0.1);
    Time delayIntervalJitter = MilliSeconds (3);

    void ApplyScenarioDefaults()
    {
        std::string scenario = digitalTwinScenario;
        std::transform(scenario.begin(), scenario.end(), scenario.begin(),
                       [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
        // This is the default scenatio so nothing to change
        if (scenario == "expeca")
        {
            digitalTwinScenario = "expeca";
            return;
        }
        // Add here if you want a parameter to be part of the scenario specific setting
        if (scenario == "5gsmart")
        {
            digitalTwinScenario = "5gsmart";
            channelScenario = "InF"; // need to change channel model as well to nyu from threegpp
            BsHeight = 0.0;
            ueHeight = 0.0;
            numerologyBwp1 = 0;
            centralFrequencyBand = 0.0;
            bandwidthHz = 0.0;
            tddPattern.clear();
            BsTxPower = 0;
            enableUlPc = false;
            NumberOfRaPreambles = 0;
            boundingBoxMinX = -45.0; 
            boundingBoxMaxX = 45.0;
            boundingBoxMinY = -45.0;
            boundingBoxMaxY = 45.0;
            controlBearerQci = 0;
            return;
        }
        NS_ABORT_MSG("Unknown digital twin scenario: " << digitalTwinScenario);
    }

    // Validate whether the parameters set are acceptable
    bool Validate () const
    {
        std::string dir = direction;
        std::transform(dir.begin(), dir.end(), dir.begin(),
                       [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
        NS_ABORT_MSG_IF(!(dir == "ul" || dir == "dl" || dir == "both"),
                        "direction must be 'ul', 'dl', or 'both'");
        std::string load = loadType;
        std::transform(load.begin(), load.end(), load.begin(),
                       [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
        NS_ABORT_MSG_IF(!(load == "none" || load == "udp" || load == "tcp"),
                        "loadType must be 'none', 'udp', or 'tcp'");
        NS_ABORT_MSG_IF(fixUlMcs > 27,
                        "fixUlMcs must be 0 (adaptive) or in [1,27] for NrEesmCcT2");
        return true;
    }
};

void CellularNetwork (const Parameters& params);

/***************************
 * Global declarations
 ***************************/

const Time appStartWindow = MilliSeconds (500);


#ifdef DELAY_BENCHMARKING_IMPLEMENTATION
NodeContainer gnbNodes;
NodeContainer ueNodes;
Ipv4InterfaceContainer ueIpIfaces;
Parameters global_params;
AsciiTraceHelper traceHelper;
TraceStreams traceStreams;
#define NR_TRACE_STREAM_ALIAS_DEF(name) Ptr<OutputStreamWrapper>& name = traceStreams.name;
NR_TRACE_STREAM_FIELDS(NR_TRACE_STREAM_ALIAS_DEF)
#undef NR_TRACE_STREAM_ALIAS_DEF
std::unordered_map<uint32_t, uint16_t> g_nodeIdToUeId;
std::unordered_map<uint16_t, uint64_t> g_rntiToImsi;
std::unordered_map<uint16_t, uint16_t> g_rntiToCellId;
std::unordered_map<uint32_t, uint32_t> g_cellBwpNumRbPerRbg;
std::unordered_map<uint32_t, uint32_t> g_cellBwpSymbolsPerSlot;
#else
extern NodeContainer gnbNodes;
extern NodeContainer ueNodes;
extern Ipv4InterfaceContainer ueIpIfaces;
extern Parameters global_params;
extern AsciiTraceHelper traceHelper;
extern TraceStreams traceStreams;
#define NR_TRACE_STREAM_ALIAS_DECL(name) extern Ptr<OutputStreamWrapper>& name;
NR_TRACE_STREAM_FIELDS(NR_TRACE_STREAM_ALIAS_DECL)
#undef NR_TRACE_STREAM_ALIAS_DECL
extern std::unordered_map<uint32_t, uint16_t> g_nodeIdToUeId;
extern std::unordered_map<uint16_t, uint64_t> g_rntiToImsi;
extern std::unordered_map<uint16_t, uint16_t> g_rntiToCellId;
extern std::unordered_map<uint32_t, uint32_t> g_cellBwpNumRbPerRbg;
extern std::unordered_map<uint32_t, uint32_t> g_cellBwpSymbolsPerSlot;
#endif


inline uint32_t
ComposeCellBwpKey(uint16_t cellId, uint8_t bwpId)
{
    return (static_cast<uint32_t>(cellId) << 16) | bwpId;
}

inline uint64_t
ResolveImsiFromPath(const std::string& path, uint16_t rnti)
{
    if (rnti == 0)
    {
        return 0;
    }

    auto it = g_rntiToImsi.find(rnti);
    if (it != g_rntiToImsi.end() && it->second != 0)
    {
        return it->second;
    }

    auto pos = path.find("/BandwidthPartMap");
    if (pos == std::string::npos)
    {
        return 0;
    }

    std::ostringstream ueMapPath;
    ueMapPath << path.substr(0, pos) << "/NrGnbRrc/UeMap/" << rnti;
    Config::MatchContainer match = Config::LookupMatches(ueMapPath.str());
    if (match.GetN() == 0)
    {
        return 0;
    }

    Ptr<NrUeManager> ueManager = match.Get(0)->GetObject<NrUeManager>();
    if (ueManager == nullptr)
    {
        return 0;
    }

    uint64_t imsi = ueManager->GetImsi();
    g_rntiToImsi[rnti] = imsi;
    // `NrUeManager` does not expose the serving cell identifier, therefore the
    // RNTI-to-cell mapping must continue to come from the RRC connection traces.
    // Avoid adding calls like ueManager->GetCellId()/GetAssociatedCellId()
    // because those APIs do not exist in ns-3's NR module.
    return imsi;
}


/***************************
 * Function Declarations
 ***************************/

uint16_t GetUeIdFromNodeId (uint16_t nodeId);
uint16_t GetNodeIdFromContext (std::string context);
uint16_t GetUeNodeIdFromIpAddr (Address ip_addr, const NodeContainer* ueNodes, const Ipv4InterfaceContainer* ueIpIfaces);
uint16_t GetImsi_from_ueId(uint16_t ueId);
uint16_t GetImsi_from_node(Ptr<ns3::Node> ue_node);    
uint16_t GetCellId_from_ueId(uint16_t ueId);
uint16_t GetCellId_from_ueNode(Ptr<ns3::Node> ue_node);    
void PrintSimInfoToFile();
void NotifyConnectionEstablishedUe (std::string context, uint64_t imsi,
                               uint16_t cellid, uint16_t rnti);
void NotifyConnectionEstablishedEnb (std::string context, uint64_t imsi,
                                uint16_t cellid, uint16_t rnti);
void udpServerTrace(std::pair<uint16_t, uint16_t> DelayPortNums,
                const Ptr<Node> &remoteHost,
                std::string context,
                Ptr<const Packet> packet, 
               const Address &from, const Address &localAddress);
void DlRxTbTraceCallback(Ptr<OutputStreamWrapper> stream,
                             std::string context,
                             RxPacketTraceParams params);
void UlRxTbTraceCallback(Ptr<OutputStreamWrapper> stream,
                             std::string context,
                             RxPacketTraceParams params);
void DlRxTbComponentTraceCallback(Ptr<OutputStreamWrapper> stream,
                                  std::string context,
                                  RxPacketTraceParams params,
                                  uint8_t lcid,
                                  uint64_t rxPduId,
                                  uint32_t rxPduBytes,
                                  uint32_t pktId,
                                  uint32_t componentBytes);
void UlRxTbComponentTraceCallback(Ptr<OutputStreamWrapper> stream,
                                  std::string context,
                                  RxPacketTraceParams params,
                                  uint8_t lcid,
                                  uint64_t rxPduId,
                                  uint32_t rxPduBytes,
                                  uint32_t pktId,
                                  uint32_t componentBytes);
void MacTbDelayTraceCallback(Ptr<OutputStreamWrapper> stream,
                             std::string context,
                             uint16_t cellId,
                             uint16_t rnti,
                             uint8_t bwpId,
                             bool isDownlink,
                             uint64_t delayNs,
                             uint32_t ipId); // codex added
void DlDataSinrTraceCallback(Ptr<OutputStreamWrapper> stream,
                             std::string context,
                             uint16_t cellId,
                             uint16_t rnti,
                             double avgSinr,
                             uint16_t bwpId);
void DlCtrlSinrTraceCallback(Ptr<OutputStreamWrapper> stream,
                             std::string context,
                             uint16_t cellId,
                             uint16_t rnti,
                             double avgSinr,
                             uint16_t bwpId);
void DlPdcpRxTraceCallback(Ptr<OutputStreamWrapper> stream,
                           std::string context,
                           uint16_t rnti,
                           uint8_t lcid,
                           uint32_t packetSize,
                           uint64_t delay,
                           uint32_t ipId); // codex added
void DlPdcpTxTraceCallback(Ptr<OutputStreamWrapper> stream,
                           std::string context,
                           uint16_t rnti,
                           uint8_t lcid,
                           uint32_t packetSize,
                           uint32_t ipId); // codex added
void UlPdcpRxTraceCallback(Ptr<OutputStreamWrapper> stream,
                           std::string context,
                           uint16_t rnti,
                           uint8_t lcid,
                           uint32_t packetSize,
                           uint64_t delay,
                           uint32_t ipId); // codex added
void UlPdcpTxTraceCallback(Ptr<OutputStreamWrapper> stream,
                           std::string context,
                           uint16_t rnti,
                           uint8_t lcid,
                           uint32_t packetSize,
                           uint32_t ipId); // codex added
void DlRlcRxTraceCallback(Ptr<OutputStreamWrapper> stream,
                          std::string context,
                          uint16_t rnti,
                          uint8_t lcid,
                          uint32_t packetSize,
                          uint64_t delay,
                          uint32_t ipId); // codex added
void DlRlcRxComponentTraceCallback(Ptr<OutputStreamWrapper> stream,
                                   std::string context,
                                   uint16_t rnti,
                                   uint8_t lcid,
                                   uint16_t rlcSn,
                                   uint32_t rlcPduBytes,
                                   uint32_t pktId,
                                   uint32_t componentBytes,
                                   uint64_t delayNs);
void DlRlcTxTraceCallback(Ptr<OutputStreamWrapper> stream,
                          std::string context,
                          uint16_t rnti,
                          uint8_t lcid,
                          uint32_t packetSize,
                          uint32_t ipId); // codex added
void DlRlcTxComponentTraceCallback(Ptr<OutputStreamWrapper> stream,
                                   std::string context,
                                   uint16_t rnti,
                                   uint8_t lcid,
                                   uint16_t rlcSn,
                                   uint32_t rlcPduBytes,
                                   uint32_t pktId,
                                   uint32_t componentBytes);
void UlRlcRxTraceCallback(Ptr<OutputStreamWrapper> stream,
                          std::string context,
                          uint16_t rnti,
                          uint8_t lcid,
                          uint32_t packetSize,
                          uint64_t delay,
                          uint32_t ipId); // codex added
void UlRlcRxComponentTraceCallback(Ptr<OutputStreamWrapper> stream,
                                   std::string context,
                                   uint16_t rnti,
                                   uint8_t lcid,
                                   uint16_t rlcSn,
                                   uint32_t rlcPduBytes,
                                   uint32_t pktId,
                                   uint32_t componentBytes,
                                   uint64_t delayNs);
void UlRlcTxTraceCallback(Ptr<OutputStreamWrapper> stream,
                          std::string context,
                          uint16_t rnti,
                          uint8_t lcid,
                          uint32_t packetSize,
                          uint32_t ipId); // codex added
void UlRlcTxComponentTraceCallback(Ptr<OutputStreamWrapper> stream,
                                   std::string context,
                                   uint16_t rnti,
                                   uint8_t lcid,
                                   uint16_t rlcSn,
                                   uint32_t rlcPduBytes,
                                   uint32_t pktId,
                                   uint32_t componentBytes);
void RlcHolDelayTraceCallback(Ptr<OutputStreamWrapper> stream, // codex added
                              std::string context,
                              uint16_t rnti,
                              uint8_t lcid,
                              uint32_t txQueueSize,
                              uint16_t txQueueHolDelay,
                              uint32_t retxQueueSize,
                              uint16_t retxQueueHolDelay,
                              uint16_t statusPduSize);
void RlcTxQueueSojournTraceCallback(Ptr<OutputStreamWrapper> stream, // codex added
                                    std::string context,
                                    uint16_t rnti,
                                    uint8_t lcid,
                                    uint32_t pduSize,
                                    uint64_t sojournNs,
                                    uint32_t ipId);
void RlcHolGrantWaitTraceCallback(Ptr<OutputStreamWrapper> stream, // codex added
                                  std::string context,
                                  uint16_t rnti,
                                  uint8_t lcid,
                                  uint32_t pduSize,
                                  uint64_t waitNs,
                                  uint32_t ipId);
void RsrpRsrqTraceCallback(Ptr<OutputStreamWrapper> stream,
                           std::string context,
                           uint16_t rnti,
                           uint16_t measuredCellId,
                           double rsrp,
                           double rsrq,
                           bool isServingCell,
                           uint8_t bwpId);
void delayTrace (Ptr<OutputStreamWrapper> stream,
                const Ptr<Node> &remoteHost,
                std::string context,
                Ptr<const Packet> packet, const Address &from, const Address &localAddress);
void loadTrace (Ptr<OutputStreamWrapper> stream,
                const std::string& proto,
                std::string context,
                Ptr<const Packet> packet,
                const Address& from,
                const Address& localAddress);
void GnbBsrTrace(Ptr<OutputStreamWrapper> stream,
                 std::string path,
                 const SfnSf sfn,
                 uint16_t nodeId,
                 uint16_t rnti,
                 uint8_t bwpId,
                 Ptr<const NrControlMessage> msg);
    
    
std::pair<ApplicationContainer, Time> 
InstallUlDelayTrafficApps (const Ptr<Node> &ue,
             const Ipv4Address &remoteHostAddr, uint16_t remotePort, Time appStartTime,
             const Ptr<UniformRandomVariable> &x,
             Time appGenerationTime,
             uint32_t packetSize,
             Time interval,
             Time jitter);
std::pair<ApplicationContainer, Time> 
InstallDlDelayTrafficApps (const Ptr<Node> &ue,
             const Ipv4Address &ueAddress,
             const Ptr<Node> &remoteHost,
             uint16_t remotePort, Time appStartTime,
             const Ptr<UniformRandomVariable> &x,
             Time appGenerationTime,
             uint32_t packetSize,
             Time interval,
             Time jitter);
void CreateTraceFiles (void);
void InitializeCellBwpNumRbPerRbg(const NetDeviceContainer& gnbNetDev);
void SetupDlMacPrbLogging();
void SetupUlMacPrbLogging();
void SetupNrTraces(const NetDeviceContainer& gnbNetDev, const Ptr<NrHelper>& helper);
void SetupSrsSinrLogging(const NetDeviceContainer& gnbNetDev, Ptr<NrHelper> helper);
std::string DciTypeToString(DciInfoElementTdma::VarTtiType type);
const char* SrStateToString(NrUeMac::SrBsrMachine state);
void UeMacCtrlTxTrace(Ptr<OutputStreamWrapper> stream,
                      const SfnSf sfn,
                      uint16_t nodeId,
                      uint16_t rnti,
                      uint8_t bwpId,
                      Ptr<const NrControlMessage> msg);
void UePhyCtrlTxTrace(Ptr<OutputStreamWrapper> stream,
                      const SfnSf sfn,
                      uint16_t nodeId,
                      uint16_t rnti,
                      uint8_t bwpId,
                      Ptr<const NrControlMessage> msg);
void UeMacStateTrace(
    Ptr<OutputStreamWrapper> stream,
    const SfnSf sfn,
    uint16_t nodeId,
    uint16_t rnti,
    uint8_t bwpId,
    NrUeMac::SrBsrMachine srState,
    std::unordered_map<uint8_t, NrMacSapProvider::BufferStatusReportParameters> ulBsrReceived,
    int retx,
    std::string nameFunc);
void UeMacRaTimeoutTrace(Ptr<OutputStreamWrapper> stream,
                         uint64_t imsi,
                         bool contention,
                         uint8_t preambleTxCount,
                         uint8_t preambleTxMax);
void DlDciTrace(std::string path,
                const SfnSf sfn,
                uint16_t cellId,
                uint16_t rnti,
                uint8_t bwpId,
                Ptr<const NrControlMessage> msg);
void UlDciTrace(std::string path,
                const SfnSf sfn,
                uint16_t cellId,
                uint16_t rnti,
                uint8_t bwpId,
                Ptr<const NrControlMessage> msg);
void SrsSinrReport(uint16_t cellId, uint16_t rnti, double sinrLinear);

/***************************
 * Function Definitions
 ***************************/

#include "nr-trace-common.h"

#ifdef DELAY_BENCHMARKING_IMPLEMENTATION

struct UeTraceIds
{
    uint16_t ueId;
    uint64_t imsi;
    uint16_t cellId;
    uint16_t rnti;
};

inline UeTraceIds
MakeUeTraceIds(uint16_t ueId)
{
    Ptr<Node> ueNode = ueNodes.Get(ueId);
    Ptr<NrUeNetDevice> ueDev = ueNode->GetDevice(0)->GetObject<NrUeNetDevice>();
    NS_ABORT_IF(ueDev == nullptr);
    Ptr<NrUeRrc> rrc = ueDev->GetRrc();
    UeTraceIds ids{ueId, ueDev->GetImsi(), 0, 0};
    if (rrc)
    {
        ids.cellId = rrc->GetCellId();
        ids.rnti = rrc->GetRnti();
    }
    return ids;
}

inline UeTraceIds
MakeUeTraceIdsFromContext(const std::string& context)
{
    return MakeUeTraceIds(GetUeIdFromNodeId(GetNodeIdFromContext(context)));
}

uint16_t
GetUeIdFromNodeId(uint16_t nodeId)
{
    auto it = g_nodeIdToUeId.find(nodeId);
    NS_ABORT_MSG_IF(it == g_nodeIdToUeId.end(),
                    "NodeId " << nodeId << " does not correspond to a UE");
    return it->second;
}

uint16_t
GetNodeIdFromContext (std::string context){
  std::string path = context.substr (10, context.length());
  std::string nodeIdStr = path.substr (0, path.find ("/"));
  uint16_t nodeId = stoi(nodeIdStr);
  return (nodeId);
}

uint16_t
GetUeNodeIdFromIpAddr (Address ip_addr, const NodeContainer* ueNodes,
                const Ipv4InterfaceContainer* ueIpIfaces
                ) {
  bool knownSender = false;
  // From the Ip addr get NetDevice and then Node
  // There is probably a way to do this through indexing 
  // but I am looping through the entire UE list to get the right node 
  for (uint32_t ueId = 0; ueId < ueNodes->GetN (); ++ueId){
    Ptr<Node> ue_node = ueNodes->Get (ueId);
    Ptr<Ipv4> ipv4 = ue_node->GetObject<Ipv4> ();
    Ipv4InterfaceAddress iaddr = ipv4->GetAddress (1,0); 
    Ipv4Address ue_addr = iaddr.GetLocal ();
    
    if (ue_addr == InetSocketAddress::ConvertFrom (ip_addr).GetIpv4 ()) {
      knownSender = true;
      return (ueId);
    }
  }
  NS_ASSERT (knownSender);
  return(666); // the number of the beast
}

uint16_t
GetImsi_from_ueId(uint16_t ueId)
{
    return MakeUeTraceIds(ueId).imsi;
}

uint16_t
GetImsi_from_node(Ptr<ns3::Node> ue_node)
{
    Ptr<NrUeNetDevice> ueDev = ue_node->GetDevice(0)->GetObject<NrUeNetDevice>();
    NS_ABORT_IF(ueDev == nullptr);
    return ueDev->GetImsi();
}

uint16_t
GetCellId_from_ueId(uint16_t ueId)
{
    return MakeUeTraceIds(ueId).cellId;
}

uint16_t
GetCellId_from_ueNode(Ptr<ns3::Node> ue_node)
{
    Ptr<NrUeNetDevice> ueDev = ue_node->GetDevice(0)->GetObject<NrUeNetDevice>();
    NS_ABORT_IF(ueDev == nullptr);
    Ptr<NrUeRrc> rrc = ueDev->GetRrc();
    return rrc ? rrc->GetCellId() : 0;
}
    
    
/**********************************
 * Connection Events 
 **********************************/
    
void
NotifyConnectionEstablishedUe (std::string context, uint64_t imsi,
                               uint16_t cellid, uint16_t rnti)
{
  std::cout << "ConnectionEstablished at "
            << " UE IMSI " << imsi
            << " to CellId " << cellid
            << " with RNTI " << rnti
            << std::endl;
}

void
NotifyConnectionEstablishedEnb (std::string context, uint64_t imsi,
                                uint16_t cellid, uint16_t rnti)
{
  std::cout << "ConnectionEstablished at "
            << " gNB CellId " << cellid
            << " with UE IMSI " << imsi
            << " RNTI " << rnti
            << std::endl;
  g_rntiToImsi[rnti] = imsi;
  g_rntiToCellId[rnti] = cellid;
}

void
ConnectPdcpRlcTracesUe(std::string context, uint64_t imsi, uint16_t cellId, uint16_t rnti)
{
    (void)imsi;
    (void)cellId;
    (void)rnti;

    const auto lastSlash = context.rfind('/');
    if (lastSlash == std::string::npos)
    {
        return;
    }

    const std::string basePath = context.substr(0, lastSlash);
    static std::unordered_set<std::string> connectedUePaths;
    if (!connectedUePaths.insert(basePath).second)
    {
        return;
    }

    Config::Connect(basePath + "/DataRadioBearerMap/*/NrPdcp/RxPDU",
                    MakeBoundCallback(&DlPdcpRxTraceCallback, dlPdcpRxStream));
    Config::Connect(basePath + "/Srb1/NrPdcp/RxPDU",
                    MakeBoundCallback(&DlPdcpRxTraceCallback, dlPdcpRxStream));
    Config::Connect(basePath + "/DataRadioBearerMap/*/NrPdcp/TxPDU",
                    MakeBoundCallback(&UlPdcpTxTraceCallback, ulPdcpTxStream));
    Config::Connect(basePath + "/Srb1/NrPdcp/TxPDU",
                    MakeBoundCallback(&UlPdcpTxTraceCallback, ulPdcpTxStream));
    Config::Connect(basePath + "/DataRadioBearerMap/*/NrRlc/RxPDU",
                    MakeBoundCallback(&DlRlcRxTraceCallback, dlRlcRxStream));
    Config::Connect(basePath + "/Srb1/NrRlc/RxPDU",
                    MakeBoundCallback(&DlRlcRxTraceCallback, dlRlcRxStream));
    Config::Connect(basePath + "/DataRadioBearerMap/*/NrRlc/RxPDUComponents",
                    MakeBoundCallback(&DlRlcRxComponentTraceCallback, dlRlcRxComponentStream));
    Config::Connect(basePath + "/Srb1/NrRlc/RxPDUComponents",
                    MakeBoundCallback(&DlRlcRxComponentTraceCallback, dlRlcRxComponentStream));
    Config::Connect(basePath + "/DataRadioBearerMap/*/NrRlc/TxPDU",
                    MakeBoundCallback(&UlRlcTxTraceCallback, ulRlcTxStream));
    Config::Connect(basePath + "/Srb1/NrRlc/TxPDU",
                    MakeBoundCallback(&UlRlcTxTraceCallback, ulRlcTxStream));
    Config::Connect(basePath + "/DataRadioBearerMap/*/NrRlc/TxPDUComponents",
                    MakeBoundCallback(&UlRlcTxComponentTraceCallback, ulRlcTxComponentStream));
    Config::Connect(basePath + "/Srb1/NrRlc/TxPDUComponents",
                    MakeBoundCallback(&UlRlcTxComponentTraceCallback, ulRlcTxComponentStream));
    // codex added
    Config::Connect(basePath + "/DataRadioBearerMap/*/NrRlc/BufferStatus",
                    MakeBoundCallback(&RlcHolDelayTraceCallback, rlcHolDelayStream));
    Config::Connect(basePath + "/Srb1/NrRlc/BufferStatus",
                    MakeBoundCallback(&RlcHolDelayTraceCallback, rlcHolDelayStream));
    // codex added
    Config::Connect(basePath + "/DataRadioBearerMap/*/NrRlc/TxQueueSojourn",
                    MakeBoundCallback(&RlcTxQueueSojournTraceCallback, rlcTxQueueSojournStream));
    Config::Connect(basePath + "/Srb1/NrRlc/TxQueueSojourn",
                    MakeBoundCallback(&RlcTxQueueSojournTraceCallback, rlcTxQueueSojournStream));
    // codex added
    Config::Connect(basePath + "/DataRadioBearerMap/*/NrRlc/TxHolGrantWait",
                    MakeBoundCallback(&RlcHolGrantWaitTraceCallback, rlcHolGrantWaitStream));
    Config::Connect(basePath + "/Srb1/NrRlc/TxHolGrantWait",
                    MakeBoundCallback(&RlcHolGrantWaitTraceCallback, rlcHolGrantWaitStream));
}

void
ConnectPdcpRlcTracesGnb(std::string context, uint64_t imsi, uint16_t cellId, uint16_t rnti)
{
    (void)imsi;
    (void)cellId;

    const auto lastSlash = context.rfind('/');
    if (lastSlash == std::string::npos)
    {
        return;
    }

    std::ostringstream uePath;
    uePath << context.substr(0, lastSlash) << "/UeMap/" << static_cast<uint32_t>(rnti);
    const std::string pathKey = uePath.str();
    static std::unordered_set<std::string> connectedGnbPaths;
    if (!connectedGnbPaths.insert(pathKey).second)
    {
        return;
    }

    Config::Connect(pathKey + "/DataRadioBearerMap/*/NrPdcp/RxPDU",
                    MakeBoundCallback(&UlPdcpRxTraceCallback, ulPdcpRxStream));
    Config::Connect(pathKey + "/Srb1/NrPdcp/RxPDU",
                    MakeBoundCallback(&UlPdcpRxTraceCallback, ulPdcpRxStream));
    Config::Connect(pathKey + "/DataRadioBearerMap/*/NrPdcp/TxPDU",
                    MakeBoundCallback(&DlPdcpTxTraceCallback, dlPdcpTxStream));
    Config::Connect(pathKey + "/Srb1/NrPdcp/TxPDU",
                    MakeBoundCallback(&DlPdcpTxTraceCallback, dlPdcpTxStream));
    Config::Connect(pathKey + "/DataRadioBearerMap/*/NrRlc/RxPDU",
                    MakeBoundCallback(&UlRlcRxTraceCallback, ulRlcRxStream));
    Config::Connect(pathKey + "/Srb0/NrRlc/RxPDU",
                    MakeBoundCallback(&UlRlcRxTraceCallback, ulRlcRxStream));
    Config::Connect(pathKey + "/Srb1/NrRlc/RxPDU",
                    MakeBoundCallback(&UlRlcRxTraceCallback, ulRlcRxStream));
    Config::Connect(pathKey + "/DataRadioBearerMap/*/NrRlc/RxPDUComponents",
                    MakeBoundCallback(&UlRlcRxComponentTraceCallback, ulRlcRxComponentStream));
    Config::Connect(pathKey + "/Srb0/NrRlc/RxPDUComponents",
                    MakeBoundCallback(&UlRlcRxComponentTraceCallback, ulRlcRxComponentStream));
    Config::Connect(pathKey + "/Srb1/NrRlc/RxPDUComponents",
                    MakeBoundCallback(&UlRlcRxComponentTraceCallback, ulRlcRxComponentStream));
    Config::Connect(pathKey + "/DataRadioBearerMap/*/NrRlc/TxPDU",
                    MakeBoundCallback(&DlRlcTxTraceCallback, dlRlcTxStream));
    Config::Connect(pathKey + "/Srb0/NrRlc/TxPDU",
                    MakeBoundCallback(&DlRlcTxTraceCallback, dlRlcTxStream));
    Config::Connect(pathKey + "/Srb1/NrRlc/TxPDU",
                    MakeBoundCallback(&DlRlcTxTraceCallback, dlRlcTxStream));
    Config::Connect(pathKey + "/DataRadioBearerMap/*/NrRlc/TxPDUComponents",
                    MakeBoundCallback(&DlRlcTxComponentTraceCallback, dlRlcTxComponentStream));
    Config::Connect(pathKey + "/Srb0/NrRlc/TxPDUComponents",
                    MakeBoundCallback(&DlRlcTxComponentTraceCallback, dlRlcTxComponentStream));
    Config::Connect(pathKey + "/Srb1/NrRlc/TxPDUComponents",
                    MakeBoundCallback(&DlRlcTxComponentTraceCallback, dlRlcTxComponentStream));
}
 

    
    
    
    
/***************************
 * Trace callbacks 
 ***************************/

// Trace Callback for UdpServer used by the delay measurement app
// since they both use UdpServers
void
udpServerTrace(std::pair<uint16_t, uint16_t> DelayPortNums,
               const Ptr<Node>& remoteHost,
               std::string context,
               Ptr<const Packet> packet,
               const Address& from,
               const Address& localAddress)
{
    const auto port = InetSocketAddress::ConvertFrom(localAddress).GetPort();
    if (port == DelayPortNums.first || port == DelayPortNums.second)
    {
        delayTrace(delayStream, remoteHost, context, packet, from, localAddress);
    }
} 
    
// This includes both the UL and DL delay trace callbacks 
void
delayTrace(Ptr<OutputStreamWrapper> stream,
           const Ptr<Node>& remoteHost,
           std::string context,
           Ptr<const Packet> packet,
           const Address& from,
           const Address& localAddress)
{
    const uint16_t receiverNodeId = GetNodeIdFromContext(context);
    const uint16_t remoteHostId = remoteHost->GetId();

    Ptr<Packet> packetCopy = packet->Copy();
    SeqTsHeader seqTs;
    if (!packetCopy->PeekHeader(seqTs))
    {
        return;
    }
    packetCopy->RemoveHeader(seqTs);

    std::string direction;
    uint16_t ueId = 0;
    if (receiverNodeId == remoteHostId)
    {
        direction = "UL";
        ueId = GetUeNodeIdFromIpAddr(from, &ueNodes, &ueIpIfaces);
    }
    else
    {
        direction = "DL";
        ueId = GetUeIdFromNodeId(receiverNodeId);
    }

    if (!InetSocketAddress::IsMatchingType(from))
    {
        return;
    }

    const auto ids = MakeUeTraceIds(ueId);
    *stream->GetStream() << Simulator::Now().GetMicroSeconds() << "\t" << direction << "\t"
                         << ids.ueId << "\t" << ids.imsi << "\t" << ids.cellId << "\t"
                         << ids.rnti << "\t" << packetCopy->GetSize() << "\t"
                         << seqTs.GetSeq() << "\t" << packetCopy->GetUid() << "\t"
                         << seqTs.GetTs().GetMicroSeconds() << "\t"
                         << (Simulator::Now() - seqTs.GetTs()).GetMicroSeconds() << std::endl;
}

// PacketSink trace for background load traffic (TCP/UDP) on remoteHost.
void
loadTrace(Ptr<OutputStreamWrapper> stream,
          const std::string& proto,
          std::string context,
          Ptr<const Packet> packet,
          const Address& from,
          const Address& localAddress)
{
    if (!IsStreamReady(stream))
    {
        return;
    }

    const uint16_t nodeId = GetNodeIdFromContext(context);
    const uint64_t nowUs = static_cast<uint64_t>(Simulator::Now().GetMicroSeconds());

    std::string srcAddr = "-";
    uint16_t srcPort = 0;
    std::string dstAddr = "-";
    uint16_t dstPort = 0;
    auto addrToString = [](const Ipv4Address& addr) -> std::string {
        std::ostringstream oss;
        addr.Print(oss);
        return oss.str();
    };
    if (InetSocketAddress::IsMatchingType(from))
    {
        InetSocketAddress src = InetSocketAddress::ConvertFrom(from);
        srcAddr = addrToString(src.GetIpv4());
        srcPort = src.GetPort();
    }
    if (InetSocketAddress::IsMatchingType(localAddress))
    {
        InetSocketAddress dst = InetSocketAddress::ConvertFrom(localAddress);
        dstAddr = addrToString(dst.GetIpv4());
        dstPort = dst.GetPort();
    }

    *stream->GetStream() << nowUs << "\t" << proto << "\t"
                         << nodeId << "\t" << srcAddr << "\t"
                         << srcPort << "\t" << dstAddr << "\t"
                         << dstPort << "\t" << packet->GetSize()
                         << std::endl;
}

// Common trace callbacks are shared in nr-trace-common.h.

void
GnbBsrTrace(Ptr<OutputStreamWrapper> stream,
             std::string path,
             const SfnSf sfn,
            uint16_t nodeId,
            uint16_t rnti,
            uint8_t bwpId,
            Ptr<const NrControlMessage> msg)
{
    if (!IsStreamReady(stream) || msg == nullptr)
    {
        return;
    }

    (void)path;

    if (msg->GetMessageType() != NrControlMessage::BSR)
    {
        return;
    }

    Ptr<NrBsrMessage> bsrMsg = DynamicCast<NrBsrMessage>(ConstCast<NrControlMessage>(msg));
    if (bsrMsg == nullptr)
    {
        return;
    }

    const MacCeElement bsr = bsrMsg->GetBsr();
    const auto& bufferStatus = bsr.m_macCeValue.m_bufferStatus;
    const int64_t nowMicros = Simulator::Now().GetMicroSeconds();

    for (size_t lcg = 0; lcg < bufferStatus.size(); ++lcg)
    {
        const uint8_t level = bufferStatus[lcg];
        // Decode SHORT-BSR level using the same table used by UE MAC/Scheduler.
        const uint32_t bytes = NrMacShortBsrCe::FromLevelToBytes(level);
        *stream->GetStream() << nowMicros << "\t" << nodeId << "\t"
                             << static_cast<uint32_t>(bwpId) << "\t" << rnti << "\t"
                             << sfn.GetFrame() << "\t"
                             << static_cast<uint32_t>(sfn.GetSubframe()) << "\t"
                             << static_cast<uint32_t>(sfn.GetSlot()) << "\t" << lcg << "\t"
                             << static_cast<uint32_t>(level) << "\t" << bytes << std::endl;
    }
}

void
InitializeCellBwpNumRbPerRbg(const NetDeviceContainer& gnbNetDev)
{
    g_cellBwpNumRbPerRbg.clear();
    g_cellBwpSymbolsPerSlot.clear();
    for (uint32_t i = 0; i < gnbNetDev.GetN(); ++i)
    {
        Ptr<NrGnbNetDevice> gnb = gnbNetDev.Get(i)->GetObject<NrGnbNetDevice>();
        if (gnb == nullptr)
        {
            continue;
        }
        const uint16_t cellId = gnb->GetCellId();
        const uint32_t bwps = gnb->GetCcMapSize();
        for (uint32_t bwpId = 0; bwpId < bwps; ++bwpId)
        {
            Ptr<NrGnbMac> mac = gnb->GetMac(bwpId);
            if (mac == nullptr)
            {
                continue;
            }
            const uint32_t key = ComposeCellBwpKey(cellId, bwpId);
            g_cellBwpNumRbPerRbg[key] = mac->GetNumRbPerRbg();

            Ptr<NrGnbPhy> phy = gnb->GetPhy(bwpId);
            if (phy != nullptr)
            {
                g_cellBwpSymbolsPerSlot[key] = phy->GetSymbolsPerSlot();
            }
        }
    }
}

void
SetupDlMacPrbLogging()
{
    if (dlMacStatsStream != nullptr)
    {
        return;
    }

    dlMacStatsStream = traceHelper.CreateFileStream("NrDlMacStats.txt");
    WriteHeader(dlMacStatsStream,
                "time_us\tcell_id\tbwp_id\timsi\trnti\tframe\tsubframe\tslot\tsym_start\t"
                "num_symbols\tsend_start_time_delta_us\tharq_id\tndi\trv\tmcs\ttb_size\t"
                "num_prbs\tmsg_type");
}

void
SetupUlMacPrbLogging()
{
    if (ulMacStatsStream != nullptr)
    {
        return;
    }

    ulMacStatsStream = traceHelper.CreateFileStream("NrUlMacStats.txt");
    WriteHeader(ulMacStatsStream,
                "time_us\tcell_id\tbwp_id\timsi\trnti\tframe\tsubframe\tslot\tsym_start\t"
                "num_symbols\tsend_start_time_delta_us\tharq_id\tndi\trv\tmcs\ttb_size\t"
                "num_prbs\tmsg_type");
}

void
SetupNrTraces(const NetDeviceContainer& gnbNetDev, const Ptr<NrHelper>& helper)
{
    Config::Connect("/NodeList/*/DeviceList/*/ComponentCarrierMapUe/*/NrUePhy/DlDataSinr",
                    MakeBoundCallback(&DlDataSinrTraceCallback, dlDataSinrStream));
    Config::Connect("/NodeList/*/DeviceList/*/ComponentCarrierMapUe/*/NrUePhy/DlCtrlSinr",
                    MakeBoundCallback(&DlCtrlSinrTraceCallback, dlCtrlSinrStream));
    Config::Connect(
        "/NodeList/*/DeviceList/*/ComponentCarrierMapUe/*/NrUePhy/SpectrumPhy/RxPacketTraceUe",
        MakeBoundCallback(&DlRxTbTraceCallback, dlRxTbTraceStream));
    Config::Connect("/NodeList/*/DeviceList/*/ComponentCarrierMapUe/*/NrUePhy/SpectrumPhy/"
                    "RxPacketTraceUeComponents",
                    MakeBoundCallback(&DlRxTbComponentTraceCallback,
                                      dlRxTbComponentTraceStream));
    Config::Connect(
        "/NodeList/*/DeviceList/*/BandwidthPartMap/*/NrGnbPhy/SpectrumPhy/RxPacketTraceGnb",
        MakeBoundCallback(&UlRxTbTraceCallback, ulRxTbTraceStream));
    Config::Connect("/NodeList/*/DeviceList/*/BandwidthPartMap/*/NrGnbPhy/SpectrumPhy/"
                    "RxPacketTraceGnbComponents",
                    MakeBoundCallback(&UlRxTbComponentTraceCallback,
                                      ulRxTbComponentTraceStream));
    Config::Connect("/NodeList/*/DeviceList/*/ComponentCarrierMapUe/*/NrUePhy/ReportUeMeasurements",
                    MakeBoundCallback(&RsrpRsrqTraceCallback, rsrpRsrqStream));
    Config::Connect("/NodeList/*/DeviceList/*/BandwidthPartMap/*/NrGnbMac/GnbMacRxedCtrlMsgsTrace",
                    MakeBoundCallback(&GnbBsrTrace, gnbBsrStream));
    Config::ConnectWithoutContext(
        "/NodeList/*/DeviceList/*/ComponentCarrierMapUe/*/NrUeMac/UeMacTxedCtrlMsgsTrace",
        MakeBoundCallback(&UeMacCtrlTxTrace, ueMacCtrlTxStream));
    Config::ConnectWithoutContext(
        "/NodeList/*/DeviceList/*/ComponentCarrierMapUe/*/NrUePhy/UePhyTxedCtrlMsgsTrace",
        MakeBoundCallback(&UePhyCtrlTxTrace, uePhyCtrlTxStream));
    Config::ConnectWithoutContext(
        "/NodeList/*/DeviceList/*/ComponentCarrierMapUe/*/NrUeMac/UeMacStateMachineTrace",
        MakeBoundCallback(&UeMacStateTrace, ueMacStateStream));
    Config::ConnectWithoutContext(
        "/NodeList/*/DeviceList/*/ComponentCarrierMapUe/*/NrUeMac/RaResponseTimeout",
        MakeBoundCallback(&UeMacRaTimeoutTrace, ueMacRaTimeoutStream));
    Config::Connect("/NodeList/*/DeviceList/*/ComponentCarrierMapUe/*/NrUePhy/SpectrumPhy/MacTbDelay",
                    MakeBoundCallback(&MacTbDelayTraceCallback, dlMacTbDelayStream));
    Config::Connect("/NodeList/*/DeviceList/*/BandwidthPartMap/*/NrGnbPhy/SpectrumPhy/MacTbDelay",
                    MakeBoundCallback(&MacTbDelayTraceCallback, ulMacTbDelayStream));
    SetupDlMacPrbLogging();
    SetupUlMacPrbLogging();
    SetupSrsSinrLogging(gnbNetDev, helper);
    Config::Connect("/NodeList/*/DeviceList/*/BandwidthPartMap/*/NrGnbPhy/GnbPhyTxedCtrlMsgsTrace",
                    MakeCallback(&DlDciTrace));
    Config::Connect("/NodeList/*/DeviceList/*/BandwidthPartMap/*/NrGnbPhy/GnbPhyTxedCtrlMsgsTrace",
                    MakeCallback(&UlDciTrace));
}

void
SetupSrsSinrLogging(const NetDeviceContainer& gnbNetDev, Ptr<NrHelper> helper)
{
    if (srsSinrStream == nullptr)
    {
        srsSinrStream = traceHelper.CreateFileStream("SrsSinrTrace.txt");
        WriteHeader(srsSinrStream, "time_us\tcell_id\trnti\tsinr_db");
    }

    for (uint32_t i = 0; i < gnbNetDev.GetN(); ++i)
    {
        Ptr<NrGnbNetDevice> gnb = gnbNetDev.Get(i)->GetObject<NrGnbNetDevice>();
        if (gnb == nullptr)
        {
            continue;
        }

        const uint32_t bwps = gnb->GetCcMapSize();
        for (uint32_t bwpId = 0; bwpId < bwps; ++bwpId)
        {
            Ptr<NrGnbPhy> phy = helper->GetGnbPhy(gnbNetDev.Get(i), bwpId);
            if (phy == nullptr)
            {
                continue;
            }
            Ptr<NrSpectrumPhy> spectrumPhy = phy->GetSpectrumPhy();
            if (spectrumPhy == nullptr)
            {
                continue;
            }
            spectrumPhy->AddSrsSinrReportCallback(MakeCallback(&SrsSinrReport));
        }
    }
}

void
UeMacCtrlTxTrace(Ptr<OutputStreamWrapper> stream,
                 const SfnSf sfn,
                 uint16_t nodeId,
                 uint16_t rnti,
                 uint8_t bwpId,
                 Ptr<const NrControlMessage> msg)
{
    if (!IsStreamReady(stream))
    {
        return;
    }
    if (msg == nullptr)
    {
        return;
    }

    const uint16_t ueId = GetUeIdFromNodeId(nodeId);
    const auto ids = MakeUeTraceIds(ueId);
    const uint16_t traceRnti = (rnti != 0) ? rnti : ids.rnti;
    *stream->GetStream()
        << Simulator::Now().GetMicroSeconds() << "\t" << nodeId << "\t" << ueId << "\t"
        << ids.imsi << "\t" << ids.cellId << "\t" << traceRnti << "\t"
        << static_cast<uint32_t>(bwpId) << "\t" << static_cast<uint32_t>(sfn.GetFrame()) << "\t"
        << static_cast<uint32_t>(sfn.GetSubframe()) << "\t" << static_cast<uint32_t>(sfn.GetSlot())
        << "\t" << ControlMsgTypeToString(msg->GetMessageType()) << std::endl;
}

void
UePhyCtrlTxTrace(Ptr<OutputStreamWrapper> stream,
                 const SfnSf sfn,
                 uint16_t nodeId,
                 uint16_t rnti,
                 uint8_t bwpId,
                 Ptr<const NrControlMessage> msg)
{
    if (!IsStreamReady(stream))
    {
        return;
    }
    if (msg == nullptr)
    {
        return;
    }

    const uint16_t ueId = GetUeIdFromNodeId(nodeId);
    const auto ids = MakeUeTraceIds(ueId);
    *stream->GetStream()
        << Simulator::Now().GetMicroSeconds() << "\t" << nodeId << "\t" << ueId << "\t"
        << ids.imsi << "\t" << ids.cellId << "\t" << rnti << "\t"
        << static_cast<uint32_t>(bwpId) << "\t" << static_cast<uint32_t>(sfn.GetFrame()) << "\t"
        << static_cast<uint32_t>(sfn.GetSubframe()) << "\t" << static_cast<uint32_t>(sfn.GetSlot())
        << "\t" << ControlMsgTypeToString(msg->GetMessageType()) << std::endl;
}

const char*
SrStateToString(NrUeMac::SrBsrMachine state)
{
    switch (state)
    {
    case NrUeMac::INACTIVE:
        return "INACTIVE";
    case NrUeMac::TO_SEND:
        return "TO_SEND";
    case NrUeMac::ACTIVE:
        return "ACTIVE";
    }
    return "UNKNOWN";
}

void
UeMacStateTrace(
    Ptr<OutputStreamWrapper> stream,
    const SfnSf sfn,
    uint16_t nodeId,
    uint16_t rnti,
    uint8_t bwpId,
    NrUeMac::SrBsrMachine srState,
    std::unordered_map<uint8_t, NrMacSapProvider::BufferStatusReportParameters> ulBsrReceived,
    int retx,
    std::string nameFunc)
{
    if (!IsStreamReady(stream))
    {
        return;
    }

    const uint16_t ueId = GetUeIdFromNodeId(nodeId);
    const auto ids = MakeUeTraceIds(ueId);
    uint64_t totalBufBytes = 0;
    for (const auto& entry : ulBsrReceived)
    {
        const auto& params = entry.second;
        totalBufBytes += params.txQueueSize;
        totalBufBytes += params.retxQueueSize;
        totalBufBytes += params.statusPduSize;
    }

    *stream->GetStream()
        << Simulator::Now().GetMicroSeconds() << "\t" << nodeId << "\t" << ueId << "\t"
        << ids.imsi << "\t" << ids.cellId << "\t" << rnti << "\t"
        << static_cast<uint32_t>(bwpId) << "\t" << static_cast<uint32_t>(sfn.GetFrame()) << "\t"
        << static_cast<uint32_t>(sfn.GetSubframe()) << "\t" << static_cast<uint32_t>(sfn.GetSlot())
        << "\t" << SrStateToString(srState) << "\t" << totalBufBytes << "\t" << retx << "\t"
        << nameFunc << std::endl;
}

void
UeMacRaTimeoutTrace(Ptr<OutputStreamWrapper> stream,
                    uint64_t imsi,
                    bool contention,
                    uint8_t preambleTxCount,
                    uint8_t preambleTxMax)
{
    if (!IsStreamReady(stream))
    {
        return;
    }
    *stream->GetStream()
        << Simulator::Now().GetMicroSeconds() << "\t" << imsi << "\t"
        << static_cast<uint32_t>(contention) << "\t" << static_cast<uint32_t>(preambleTxCount)
        << "\t" << static_cast<uint32_t>(preambleTxMax) << std::endl;
}

std::string
DciTypeToString(DciInfoElementTdma::VarTtiType type)
{
    switch (type)
    {
    case DciInfoElementTdma::SRS:
        return "SRS";
    case DciInfoElementTdma::DATA:
        return "DATA";
    case DciInfoElementTdma::CTRL:
        return "CTRL";
    case DciInfoElementTdma::MSG3:
        return "MSG3";
    default:
        return "UNKNOWN";
    }
}

void
DlDciTrace(std::string path,
           const SfnSf sfn,
           uint16_t cellId,
           uint16_t rnti,
           uint8_t bwpId,
           Ptr<const NrControlMessage> msg)
{
    (void)path;

    if (msg == nullptr || msg->GetMessageType() != NrControlMessage::DL_DCI)
    {
        return;
    }

    Ptr<NrDlDciMessage> dlDciMsg = DynamicCast<NrDlDciMessage>(ConstCast<NrControlMessage>(msg));
    if (dlDciMsg == nullptr)
    {
        return;
    }

    std::shared_ptr<DciInfoElementTdma> dci = dlDciMsg->GetDciInfoElement();
    if (!dci)
    {
        return;
    }
    const uint16_t ueRnti = dci->m_rnti;
    if (ueRnti == 0)
    {
        return;
    }

    const uint32_t key = ComposeCellBwpKey(cellId, bwpId);
    auto rbIt = g_cellBwpNumRbPerRbg.find(key);
    const uint32_t rbPerRbg = (rbIt != g_cellBwpNumRbPerRbg.end()) ? rbIt->second : 0;
    auto symIt = g_cellBwpSymbolsPerSlot.find(key);
    const uint32_t symbolsPerSlot = (symIt != g_cellBwpSymbolsPerSlot.end()) ? symIt->second : 14;
    uint32_t rbgCount = std::count(dci->m_rbgBitmask.begin(), dci->m_rbgBitmask.end(), true);
    uint32_t numPrbs = rbgCount * rbPerRbg;
    const std::string msgType = DciTypeToString(dci->m_type);
    const double sendStartDeltaUs = UlSendStartDeltaMicroseconds(dlDciMsg->GetKDelay(),
                                                                 sfn.GetNumerology(),
                                                                 dci->m_symStart,
                                                                 symbolsPerSlot);

    if (!IsStreamReady(dlMacStatsStream))
    {
        return;
    }

    uint64_t imsi = ResolveImsiFromPath(path, ueRnti);

    *dlMacStatsStream->GetStream()
        << Simulator::Now().GetMicroSeconds() << "\t" << cellId << "\t"
        << static_cast<uint32_t>(bwpId)
        << "\t" << imsi << "\t" << ueRnti << "\t" << static_cast<uint32_t>(sfn.GetFrame()) << "\t"
        << static_cast<uint32_t>(sfn.GetSubframe()) << "\t" << static_cast<uint32_t>(sfn.GetSlot())
        << "\t" << static_cast<uint32_t>(dci->m_symStart) << "\t"
        << static_cast<uint32_t>(dci->m_numSym) << "\t" << sendStartDeltaUs << "\t"
        << static_cast<uint32_t>(dci->m_harqProcess) << "\t" << static_cast<uint32_t>(dci->m_ndi)
        << "\t" << static_cast<uint32_t>(dci->m_rv) << "\t" << static_cast<uint32_t>(dci->m_mcs)
        << "\t" << dci->m_tbSize << "\t" << numPrbs << "\t" << msgType << std::endl;
}

void
UlDciTrace(std::string path,
           const SfnSf sfn,
           uint16_t cellId,
           uint16_t rnti,
           uint8_t bwpId,
           Ptr<const NrControlMessage> msg)
{
    (void)path;

    if (msg == nullptr || msg->GetMessageType() != NrControlMessage::UL_DCI)
    {
        return;
    }

    Ptr<NrUlDciMessage> ulDciMsg = DynamicCast<NrUlDciMessage>(ConstCast<NrControlMessage>(msg));
    if (ulDciMsg == nullptr)
    {
        return;
    }

    std::shared_ptr<DciInfoElementTdma> dci = ulDciMsg->GetDciInfoElement();
    if (!dci)
    {
        return;
    }
    const uint16_t ueRnti = dci->m_rnti;
    if (ueRnti == 0)
    {
        return;
    }

    const uint32_t key = ComposeCellBwpKey(cellId, bwpId);
    auto rbIt = g_cellBwpNumRbPerRbg.find(key);
    const uint32_t rbPerRbg = (rbIt != g_cellBwpNumRbPerRbg.end()) ? rbIt->second : 0;
    auto symIt = g_cellBwpSymbolsPerSlot.find(key);
    const uint32_t symbolsPerSlot = (symIt != g_cellBwpSymbolsPerSlot.end()) ? symIt->second : 14;
    uint32_t rbgCount = std::count(dci->m_rbgBitmask.begin(), dci->m_rbgBitmask.end(), true);
    uint32_t numPrbs = rbgCount * rbPerRbg;
    const std::string msgType = DciTypeToString(dci->m_type);
    const double sendStartDeltaUs = UlSendStartDeltaMicroseconds(ulDciMsg->GetKDelay(),
                                                                 sfn.GetNumerology(),
                                                                 dci->m_symStart,
                                                                 symbolsPerSlot);

    if (!IsStreamReady(ulMacStatsStream))
    {
        return;
    }

    uint64_t imsi = ResolveImsiFromPath(path, ueRnti);

    *ulMacStatsStream->GetStream()
        << Simulator::Now().GetMicroSeconds() << "\t" << cellId << "\t"
        << static_cast<uint32_t>(bwpId)
        << "\t" << imsi << "\t" << ueRnti << "\t" << static_cast<uint32_t>(sfn.GetFrame()) << "\t"
        << static_cast<uint32_t>(sfn.GetSubframe()) << "\t" << static_cast<uint32_t>(sfn.GetSlot())
        << "\t" << static_cast<uint32_t>(dci->m_symStart) << "\t"
        << static_cast<uint32_t>(dci->m_numSym) << "\t" << sendStartDeltaUs << "\t"
        << static_cast<uint32_t>(dci->m_harqProcess) << "\t" << static_cast<uint32_t>(dci->m_ndi)
        << "\t" << static_cast<uint32_t>(dci->m_rv) << "\t" << static_cast<uint32_t>(dci->m_mcs)
        << "\t" << dci->m_tbSize << "\t" << numPrbs << "\t" << msgType << std::endl;
}

void
SrsSinrReport(uint16_t cellId, uint16_t rnti, double sinrLinear)
{
    if (!IsStreamReady(srsSinrStream))
    {
        return;
    }

    // guard against log10(0)
    const double clampedSinr = std::max(sinrLinear, 1e-12);
    const double sinrDb = 10.0 * std::log10(clampedSinr);

    *srsSinrStream->GetStream() << Simulator::Now().GetMicroSeconds() << "\t" << cellId << "\t"
                                << rnti << "\t" << sinrDb << std::endl;
}
    
class JitteredUdpClient : public Application
{
  public:
    JitteredUdpClient()
        : m_size(1024),
          m_interval(Seconds(1)),
          m_jitter(Seconds(0)),
          m_sent(0)
    {
        m_rng = CreateObject<UniformRandomVariable>();
    }

    void SetRemote(const Address& addr)
    {
        m_peer = addr;
    }

    void SetPacketSize(uint32_t size)
    {
        m_size = size;
    }

    void SetInterval(Time interval)
    {
        m_interval = interval;
    }

    void SetJitter(Time jitter)
    {
        m_jitter = jitter;
    }

  private:
    void StartApplication() override
    {
        if (!m_socket)
        {
            auto tid = TypeId::LookupByName("ns3::UdpSocketFactory");
            m_socket = Socket::CreateSocket(GetNode(), tid);
            NS_ABORT_MSG_IF(m_peer.IsInvalid(), "Remote address not properly set");
            if (InetSocketAddress::IsMatchingType(m_peer))
            {
                if (m_socket->Bind() == -1)
                {
                    NS_FATAL_ERROR("Failed to bind socket");
                }
            }
            else if (Inet6SocketAddress::IsMatchingType(m_peer))
            {
                if (m_socket->Bind6() == -1)
                {
                    NS_FATAL_ERROR("Failed to bind socket");
                }
            }
            else
            {
                NS_ASSERT_MSG(false, "Incompatible address type: " << m_peer);
            }
            m_socket->Connect(m_peer);
            m_socket->SetRecvCallback(MakeNullCallback<void, Ptr<Socket>>());
            m_socket->SetAllowBroadcast(true);
        }
        m_sendEvent = Simulator::Schedule(Seconds(0), &JitteredUdpClient::Send, this);
    }

    void StopApplication() override
    {
        Simulator::Cancel(m_sendEvent);
    }

    void Send()
    {
        NS_ASSERT(m_sendEvent.IsExpired());
        SeqTsHeader seqTs;
        seqTs.SetSeq(m_sent);
        NS_ABORT_IF(m_size < seqTs.GetSerializedSize());
        auto p = Create<Packet>(m_size - seqTs.GetSerializedSize());
        p->AddHeader(seqTs);
        m_socket->Send(p);
        ++m_sent;

        double jitterSeconds = 0.0;
        if (m_jitter.IsPositive())
        {
            jitterSeconds = m_rng->GetValue(-m_jitter.GetSeconds(), m_jitter.GetSeconds());
        }
        Time next = m_interval + Seconds(jitterSeconds);
        if (next <= MicroSeconds(0))
        {
            next = MicroSeconds(1);
        }
        m_sendEvent = Simulator::Schedule(next, &JitteredUdpClient::Send, this);
    }

    Ptr<Socket> m_socket;
    Address m_peer;
    uint32_t m_size;
    Time m_interval;
    Time m_jitter;
    uint32_t m_sent;
    EventId m_sendEvent;
    Ptr<UniformRandomVariable> m_rng;
};

 /***********************************************
 * Install client applications
 **********************************************/
std::pair<ApplicationContainer, Time>
InstallUlDelayTrafficApps (const Ptr<Node> &ue,
             const Ipv4Address &remoteHostAddr, uint16_t remotePort, Time appStartTime,
             const Ptr<UniformRandomVariable> &x,
             Time appGenerationTime,
             uint32_t packetSize,
             Time interval,
             Time jitter)
{
  ApplicationContainer app;
  Ptr<JitteredUdpClient> client = CreateObject<JitteredUdpClient>();
  client->SetRemote(InetSocketAddress(remoteHostAddr, remotePort));
  client->SetPacketSize(packetSize);
  client->SetInterval(interval);
  client->SetJitter(jitter);
  ue->AddApplication(client);
  app.Add(client);

  double start = x->GetValue (appStartTime.GetMilliSeconds (),
                              (appStartTime + appStartWindow).GetMilliSeconds ());
  Time startTime = MilliSeconds (start);
  app.Start (startTime);
  app.Stop (startTime + appGenerationTime);
  return std::make_pair (app, startTime);
}

std::pair<ApplicationContainer, Time>
InstallDlDelayTrafficApps (const Ptr<Node> &ue,
             const Ipv4Address &ueAddress,
             const Ptr<Node> &remoteHost,
             uint16_t remotePort, Time appStartTime,
             const Ptr<UniformRandomVariable> &x,
             Time appGenerationTime,
             uint32_t packetSize,
             Time interval,
             Time jitter)
{
  ApplicationContainer app;
  Ptr<JitteredUdpClient> client = CreateObject<JitteredUdpClient>();
  client->SetRemote(InetSocketAddress(ueAddress, remotePort));
  client->SetPacketSize(packetSize);
  client->SetInterval(interval);
  client->SetJitter(jitter);
  remoteHost->AddApplication(client);
  app.Add(client);

  double start = x->GetValue (appStartTime.GetMilliSeconds (),
                              (appStartTime + appStartWindow).GetMilliSeconds ());
  Time startTime = MilliSeconds (start);
  app.Start (startTime);
  app.Stop (startTime + appGenerationTime);
  return std::make_pair (app, startTime);
}
  
 /***********************************************
 * Create trace files and write column names
 **********************************************/
void CreateTraceFiles (void)
{
    simInfoStream = traceHelper.CreateFileStream ("sim_info.txt"); 

    if (global_params.includeUlDelayApp || global_params.includeDlDelayApp)
    {
        delayStream = traceHelper.CreateFileStream ("delay_trace.txt");
        WriteHeader(delayStream,
                    "time_us\tdirection\tue_id\timsi\tcell_id\trnti\tpkt_size\tseq_num\tpkt_uid\t"
                    "tx_time_us\tdelay_us");
    }
    if (global_params.loadType != "none")
    {
        loadTraceStream = traceHelper.CreateFileStream("load_trace.txt");
        WriteHeader(loadTraceStream,
                    "time_us\tproto\tnode_id\tsrc_ip\tsrc_port\tdst_ip\tdst_port\tpacket_size");
    }
    dlRxTbTraceStream = traceHelper.CreateFileStream("DlRxTbTrace.txt");
    WriteHeader(dlRxTbTraceStream,
                "time_us\tframe\tsubframe\tslot\tsym_start\tnum_symbols\tcell_id\tbwp_id\t"
                "rnti\ttb_size\tmcs\trank\trv\tsinr_db\tcqi\tcorrupt\ttbler");
    ulRxTbTraceStream = traceHelper.CreateFileStream("UlRxTbTrace.txt");
    WriteHeader(ulRxTbTraceStream,
                "time_us\tframe\tsubframe\tslot\tsym_start\tnum_symbols\tcell_id\tbwp_id\t"
                "rnti\ttb_size\tmcs\trank\trv\tsinr_db\tcqi\tcorrupt\ttbler");
    dlRxTbComponentTraceStream = traceHelper.CreateFileStream("DlRxTbComponentTrace.txt");
    WriteHeader(dlRxTbComponentTraceStream,
                "time_us\trx_pdu_id\tframe\tsubframe\tslot\tsym_start\tnum_symbols\tcell_id\t"
                "bwp_id\trnti\tlcid\ttb_size\trx_pdu_bytes\tmcs\trank\trv\tsinr_db\tcqi\t"
                "corrupt\ttbler\tpkt_id\tcomponent_bytes");
    ulRxTbComponentTraceStream = traceHelper.CreateFileStream("UlRxTbComponentTrace.txt");
    WriteHeader(ulRxTbComponentTraceStream,
                "time_us\trx_pdu_id\tframe\tsubframe\tslot\tsym_start\tnum_symbols\tcell_id\t"
                "bwp_id\trnti\tlcid\ttb_size\trx_pdu_bytes\tmcs\trank\trv\tsinr_db\tcqi\t"
                "corrupt\ttbler\tpkt_id\tcomponent_bytes");
    dlDataSinrStream = traceHelper.CreateFileStream("DlDataSinr.txt");
    WriteHeader(dlDataSinrStream, "time_us\tcell_id\trnti\tbwp_id\tsinr_db");
    dlCtrlSinrStream = traceHelper.CreateFileStream("DlCtrlSinr.txt");
    WriteHeader(dlCtrlSinrStream, "time_us\tcell_id\trnti\tbwp_id\tsinr_db");
    dlPdcpRxStream = traceHelper.CreateFileStream("NrDlPdcpRxStats.txt");
    WriteHeader(dlPdcpRxStream,
                "time_us\tcell_id\trnti\tlcid\tpkt_id\tpacket_size\tdelay_us"); // codex added
    ulPdcpRxStream = traceHelper.CreateFileStream("NrUlPdcpRxStats.txt");
    WriteHeader(ulPdcpRxStream,
                "time_us\tcell_id\trnti\tlcid\tpkt_id\tpacket_size\tdelay_us"); // codex added
    dlPdcpTxStream = traceHelper.CreateFileStream("NrDlPdcpTxStats.txt");
    WriteHeader(dlPdcpTxStream, "time_us\tcell_id\trnti\tlcid\tpkt_id\tpacket_size"); // codex added
    ulPdcpTxStream = traceHelper.CreateFileStream("NrUlPdcpTxStats.txt");
    WriteHeader(ulPdcpTxStream, "time_us\tcell_id\trnti\tlcid\tpkt_id\tpacket_size"); // codex added
    dlRlcRxStream = traceHelper.CreateFileStream("NrDlRlcRxStats.txt");
    WriteHeader(dlRlcRxStream,
                "time_us\tcell_id\trnti\tlcid\tpkt_id\tpacket_size\tdelay_us"); // codex added
    ulRlcRxStream = traceHelper.CreateFileStream("NrUlRlcRxStats.txt");
    WriteHeader(ulRlcRxStream,
                "time_us\tcell_id\trnti\tlcid\tpkt_id\tpacket_size\tdelay_us"); // codex added
    dlRlcTxStream = traceHelper.CreateFileStream("NrDlRlcTxStats.txt");
    WriteHeader(dlRlcTxStream, "time_us\tcell_id\trnti\tlcid\tpkt_id\tpacket_size"); // codex added
    ulRlcTxStream = traceHelper.CreateFileStream("NrUlRlcTxStats.txt");
    WriteHeader(ulRlcTxStream, "time_us\tcell_id\trnti\tlcid\tpkt_id\tpacket_size"); // codex added
    dlRlcRxComponentStream = traceHelper.CreateFileStream("NrDlRlcRxComponentStats.txt");
    WriteHeader(dlRlcRxComponentStream,
                "time_us\tcell_id\trnti\tlcid\trlc_sn\trlc_pdu_bytes\tpkt_id\tcomponent_bytes\t"
                "delay_us");
    ulRlcRxComponentStream = traceHelper.CreateFileStream("NrUlRlcRxComponentStats.txt");
    WriteHeader(ulRlcRxComponentStream,
                "time_us\tcell_id\trnti\tlcid\trlc_sn\trlc_pdu_bytes\tpkt_id\tcomponent_bytes\t"
                "delay_us");
    dlRlcTxComponentStream = traceHelper.CreateFileStream("NrDlRlcTxComponentStats.txt");
    WriteHeader(dlRlcTxComponentStream,
                "time_us\tcell_id\trnti\tlcid\trlc_sn\trlc_pdu_bytes\tpkt_id\tcomponent_bytes");
    ulRlcTxComponentStream = traceHelper.CreateFileStream("NrUlRlcTxComponentStats.txt");
    WriteHeader(ulRlcTxComponentStream,
                "time_us\tcell_id\trnti\tlcid\trlc_sn\trlc_pdu_bytes\tpkt_id\tcomponent_bytes");
    dlMacTbDelayStream = traceHelper.CreateFileStream("DlMacTbDelayTrace.txt"); // codex added
    WriteHeader(dlMacTbDelayStream,
                "time_us\tcell_id\tbwp_id\trnti\tpkt_id\tmac_tb_delay_us"); // codex added
    ulMacTbDelayStream = traceHelper.CreateFileStream("UlMacTbDelayTrace.txt"); // codex added
    WriteHeader(ulMacTbDelayStream,
                "time_us\tcell_id\tbwp_id\trnti\tpkt_id\tmac_tb_delay_us"); // codex added
    rlcHolDelayStream = traceHelper.CreateFileStream("RlcHolDelayTrace.txt"); // codex added
    WriteHeader(rlcHolDelayStream,
                "time_us\tcell_id\trnti\tlcid\ttx_queue_bytes\ttx_queue_hol_us\t"
                "retx_queue_bytes\tretx_queue_hol_us\tstatus_pdu_bytes"); // codex added
    rlcTxQueueSojournStream = traceHelper.CreateFileStream("RlcTxQueueSojournTrace.txt"); // codex added
    WriteHeader(rlcTxQueueSojournStream,
                "time_us\tcell_id\trnti\tlcid\tpkt_id\tpdu_size\tpre_hol_wait_us"); // codex added
    rlcHolGrantWaitStream = traceHelper.CreateFileStream("RlcHolGrantWaitTrace.txt"); // codex added
    WriteHeader(rlcHolGrantWaitStream,
                "time_us\tcell_id\trnti\tlcid\tpkt_id\tpdu_size\thol_grant_wait_us"); // codex added
    rsrpRsrqStream = traceHelper.CreateFileStream("RsrpRsrqTrace.txt");
    WriteHeader(rsrpRsrqStream,
                "time_us\tue_id\timsi\tserving_cell_id\tmeasured_cell_id\tbwp_id\trnti\t"
                "rsrp_dbm\tserving_cell");
    gnbBsrStream = traceHelper.CreateFileStream("GnbBsrTrace.txt");
    WriteHeader(gnbBsrStream,
                "time_us\tnode_id\tbwp_id\trnti\tframe\tsubframe\tslot\tlcg\tbsr_level\t"
                "queue_bytes");
    ueMacCtrlTxStream = traceHelper.CreateFileStream("UeMacCtrlTxTrace.txt");
    WriteHeader(ueMacCtrlTxStream,
                "time_us\tnode_id\tue_id\timsi\tcell_id\trnti\tbwp_id\tframe\tsubframe\t"
                "slot\tmsg_type");
    uePhyCtrlTxStream = traceHelper.CreateFileStream("UePhyCtrlTxTrace.txt");
    WriteHeader(uePhyCtrlTxStream,
                "time_us\tnode_id\tue_id\timsi\tcell_id\trnti\tbwp_id\tframe\tsubframe\t"
                "slot\tmsg_type");
    ueMacStateStream = traceHelper.CreateFileStream("UeMacStateTrace.txt");
    WriteHeader(ueMacStateStream,
                "time_us\tnode_id\tue_id\timsi\tcell_id\trnti\tbwp_id\tframe\tsubframe\t"
                "slot\tsr_state\tbuffer_bytes\tretx\tcallsite");
    ueMacRaTimeoutStream = traceHelper.CreateFileStream("UeMacRaTimeoutTrace.txt");
    WriteHeader(ueMacRaTimeoutStream,
                "time_us\timsi\tcontention\tpreamble_tx_count\tpreamble_tx_max");

}    
    
// Print the scenario parameters into a file for the parsing and visualisation scripts to use 
void PrintSimInfoToFile()
{
    std::cout << "Inside PrintSimInfoToFile function that prints to sim_info.txt file" << std::endl;
    *simInfoStream->GetStream() << "parameter,value\n";
    *simInfoStream->GetStream() << "gnb_count," << gnbNodes.GetN() << std::endl;
    *simInfoStream->GetStream() << "ue_count," << ueNodes.GetN() << std::endl;
    *simInfoStream->GetStream()
        << "simulation_time_seconds," << global_params.appGenerationTime.GetSeconds() << std::endl;
    *simInfoStream->GetStream() << "rand_seed," << global_params.randSeed << std::endl;
    *simInfoStream->GetStream()
        << "ul_delay_app_installed," << (global_params.includeUlDelayApp ? 1 : 0) << std::endl;
    *simInfoStream->GetStream()
        << "dl_delay_app_installed," << (global_params.includeDlDelayApp ? 1 : 0) << std::endl;
    *simInfoStream->GetStream() << "fix_ul_mcs,"
                                << (global_params.fixUlMcs == 0
                                        ? std::string("adaptive")
                                        : std::to_string(global_params.fixUlMcs))
                                << std::endl;
    *simInfoStream->GetStream() << "enable_bootstrap_mcs_limit,"
                                << (global_params.enableBootstrapMcsLimit ? 1 : 0) << std::endl;
    if (global_params.includeUlDelayApp || global_params.includeDlDelayApp)
    {
        *simInfoStream->GetStream() << "delay_pkt_interval_seconds,"
                                    << global_params.delayInterval.As(Time::S) << std::endl;
    }
    std::cout << "Exiting PrintSimInfoToFile function that prints to sim_info.txt file" << std::endl;
}

std::ostream&
operator<< (std::ostream& os, const Parameters& parameters)
{
    os << "Simulation parameters:\n"
       << "  numUes: " << parameters.numUes << std::endl
       << "  loadType: " << parameters.loadType << std::endl
       << "  direction: " << parameters.direction << std::endl
       << "  cbrLoadMbps: " << parameters.cbrLoadMbps << std::endl
       << "  fixUlMcs: "
       << (parameters.fixUlMcs == 0 ? std::string("adaptive")
                                    : std::to_string(parameters.fixUlMcs))
       << std::endl
       << "  enableBootstrapMcsLimit: " << parameters.enableBootstrapMcsLimit << std::endl
       << "  centralFrequencyHz: " << parameters.centralFrequencyBand << std::endl
       << "  bandwidthHz: " << parameters.bandwidthHz << std::endl
       << "  numerology: " << parameters.numerologyBwp1 << std::endl
       << "  numRbPerRbg: " << parameters.numRbPerRbg << std::endl
       << "  tddPattern: " << parameters.tddPattern << std::endl
       << "  BsTxPower: " << parameters.BsTxPower << " dBm\n"
       << "  includeUlDelayApp: " << parameters.includeUlDelayApp << std::endl
       << "  includeDlDelayApp: " << parameters.includeDlDelayApp << std::endl;
    return os;
}

#endif // DELAY_BENCHMARKING_IMPLEMENTATION

} // namespace ns3

#endif // DELAY_BENCHMARKING_FUNCTION_H
