import json
import os

from models import Router, Interface, Network, Bgp, Neighbor, VRF
from jinja2 import Environment, FileSystemLoader

ipNetworkUsed = {}

def handle_network(network):
    ASList = {}
    lastSubnetId = 0
    for As in network['AS']:
        routerAsList = {}
        
        for router in As['routers']:

            routerObj = Router()
            routerObj.id = router['id']
            routerObj.hostname = router['hostName']

            intLoopback = Interface()
            intLoopback.name = 'Loopback0'
            intLoopback.address = (router['id'] + ".")*3 + router['id']
            intLoopback.ospfArea = "0"
            routerObj.loopback = intLoopback
            routerObj.interfaces = []

            for connection in router['connections']:
                interface = Interface()
                interface.id = connection["interface"]
                interface.name = "GigabitEthernet" + interface.id + "/0"

                if (router["id"], connection['router']) in ipNetworkUsed:
                    interface.prefix = ipNetworkUsed[(router["id"], connection['router'])]
                else:
                    lastSubnetId += 1
                    interface.prefix = lastSubnetId
                    ipNetworkUsed[(connection['router'], router["id"])] = lastSubnetId

                interface.address = "10.1." + str(interface.prefix) + "." + router['id']
                interface.addressnet = "10.1." + str(interface.prefix) + "." + "0"
                if connection['ospfArea']:
                    interface.ospfArea = connection['ospfArea']
                    routerObj.ospf = True
                # A tuple with (neighbor_name, neighbor_id)
                interface.neighbor = (
                    [k for k, v in network['routerMap'].items() if v == connection["router"]][0],
                    connection["router"]
                    )
                
                routerObj.interfaces.append(interface)

            bgp = Bgp()
            bgp.number = As['number']
            bgp.neighbors = []
            for bgpNeighbor in router["bgpNeighbors"]:
                neighbor = Neighbor()
                neighbor.loopback = bgpNeighbor
                for AsBis in network['AS']:
                    neighborId = bgpNeighbor.split(".")[0]
                    for r in AsBis["routers"]:
                        if r["id"] == neighborId:
                            neighbor.AS = AsBis["number"]
                            break
                bgp.neighbors.append(neighbor)
            
            routerObj.bgp = bgp

            routerAsList[routerObj.id] = routerObj

        ASList[As['number']] = routerAsList

    return ASList












if __name__ == '__main__':
    environment = Environment(loader=FileSystemLoader('Automate/templates/'), trim_blocks = True, lstrip_blocks = True)
    template = environment.get_template('config_template.txt')
    f = open('Automate/network.json','r')
    load = json.load(f)
    ASList = handle_network(load)

    routers = {}

    CE_routers_ip = {}
    for AS in ASList.values():
        for router in AS.values():
            routers[router.hostname] = router
            if router.hostname.startswith("CE"):
                for interface in router.interfaces:
                    if interface.neighbor[0].startswith("PE"):
                        CE_routers_ip[router.loopback.address] = interface.address
    for AS in ASList.values():
        for router in AS.values():
            if router.hostname.startswith("PE"):
                for n in router.bgp.neighbors:
                    if n.loopback in CE_routers_ip.keys():
                        n.ip = CE_routers_ip[n.loopback]

    inverseRouterMap = {v:k for k,v in load["routerMap"].items()}
    # for vrf in load["VRFs"]:
    #     for client in vrf["link"]:
    #         vrfData = VRF()
    #         vrfData.
    PE_routers = filter(lambda k:k.startswith("PE"), routers.keys())
    for PE_name in PE_routers:
        PE_router = routers[PE_name]
        vrfList = []
        siteCount = 0
        for vrf in load["VRFs"]:
            vrf_edges = vrf["link"]
            for vrf_edge in vrf_edges:
                if vrf_edge["PEid"] == PE_router.id:
                    vrfObj = VRF()
                    siteCount += 1
                    vrfObj.site = f"site{siteCount}"
                    vrfInterface = list(filter(lambda i:i.id == vrf_edge["interface"], PE_router.interfaces))[0]
                    rd_CE_name = vrfInterface.neighbor[0]
                    vrfInterface.vrf_site = vrfObj.site
                    vrfObj.rd_As = routers[rd_CE_name].bgp.number
                    vrfObj.id = vrf["id"]
                    vrfObj.interface = vrfInterface

                    route_target_PE = routers[inverseRouterMap[vrf_edges[0]["PEid"]]]
                    target_router = routers[list(filter(lambda i:i.id == vrf_edges[0]["interface"], route_target_PE.interfaces))[0].neighbor[0]]
                    vrfObj.target_As = target_router.bgp.number

                    vrfList.append(vrfObj)
        
        PE_router.vrfs = vrfList


    for AS in ASList.values():
        for router in AS.values():
            print(router.hostname)

            path = r"C:\Users\thaiv\OneDrive\Desktop\NAS\NAS_test\project-files\dynamips"
            cfg_file = 'i' + str(load['routerMap'][router.hostname]) + "_startup-config.cfg"
            real_path=""
            for root, dirs, files in os.walk(path):
                if cfg_file in files:
                    real_path = os.path.join(root, cfg_file)
            f2 = open(real_path, "w")
            f2.write(template.render(router=router))
            f2.close()
            # f = open(router.hostname + ".cfg", "w")
            # f.write(template.render(router=router))
            # f.close()

            final_config_path = r"C:\Users\thaiv\OneDrive\Desktop\NAS\final_config"
            os.makedirs(final_config_path, exist_ok=True)         
            final_file_path = os.path.join(final_config_path, router.hostname + ".cfg")
            f = open(final_file_path, "w")
            f.write(template.render(router=router))
            f.close()

    f.close()

    print("Check the final_config folder for the final configuration files")
