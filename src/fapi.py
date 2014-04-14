#!/usr/bin/env python

# 2014 (c) Paul C. Buetow

import argparse
import base64
import bigsuds
import getpass 
import pprint
import socket
import sys
import re

from os.path import expanduser
from inspect import isfunction

import ConfigParser

__program__ = 'fapi'
__version__ = 'VERSION_DEVEL' # Replaced by a Makefile tsubet
__prompt__  = '>>>' # Default prompt


def print_synopsis():
    ''' Prints the full Synopsis string '''

    print "\n".join([
        'This is %s version %s' % (__program__, __version__),
        '',
        'Synopsis:',
        ' fapi monitor',
        ' fapi monitor MONITORNAME get desc|state',
        ' fapi node',
        ' fapi node NODENAME create|delete',
        ' fapi node NODENAME get detail|status',
        ' fapi pool',
        ' fapi pool POOLNAME add member MEMBERNAME:PORT',
        ' fapi pool POOLNAME add monitor MONITORNAME',
        ' fapi pool POOLNAME create [LIST,OF,POOL,MEMBERS:PORT]',
        ' fapi pool POOLNAME delete',
        ' fapi pool POOLNAME del member MEMBERNAME:PORT',
        ' fapi pool POOLNAME del monitors',
        ' fapi pool POOLNAME get detail|lbmethod|members|monitor|status',
        ' fapi pool POOLNAME set lbmethod LBMETHOD',
        ' fapi vserver',
        ' fapi vserver VSERVERNAME create [protocol] [profile] [poolname] [mask]',
        ' fapi vserver VSERVERNAME delete',
        ' fapi vserver VSERVERNAME get brief|detail|status',
        ' fapi vserver VSERVERNAME set nat|pat disabled|enabled',
        ' fapi vserver VSERVERNAME set pool POOLNAME',
        ' fapi vserver VSERVERNAME set snat none',
    ])



class Fapi(object):
    ''' The main F5 API Tool Object '''

    def __init__(self, args):
        ''' Initialize the config file, username and password '''

        self._args = args
        self._config = ConfigParser.ConfigParser()
        self._config.read(args.C)
        self._partition = self._config.get('fapi', 'partition')


    def __login(self):
        ''' Logs into the F5 BigIP SOAP API and changes the partition'''

        c = self._config
        a = self._args

        if c.has_option('fapi', 'username'):
            username = c.get('fapi', 'username')
        else:
            username = getpass.getuser()
        if c.has_option('fapi', 'password64'):
            password = base64.decodestring(c.get('fapi', 'password64'))
        else:
            prompt = 'Enter API password for user %s: ' % username
            password = getpass.getpass(prompt)
        self.info('Login to BigIP API with user %s' % username)

        # Try a comma separated lists of F5 boxes, use the first one
        err = None
        for hostname in c.get('fapi', 'hostnames').split(','):
            try:
                self.info('Trying to login to \'%s\'' % hostname)
                self._f5 = bigsuds.BIGIP(hostname = hostname,
                                         username = username,
                                         password = password)
                self._f5.Management.Partition.set_active_partition(self._partition)
                self.info('Set partition to \'%s\'' % self._partition)
                err = None
                break
            except Exception, e:
                err = '%s:%s' % (hostname, e)
                pass

        if err:
            self.info(err)
            sys.exit(2)


    def info(self, message):
        ''' Prints an informational message to stderr '''

        if self._args.v: print >> sys.stderr, '%s %s' % (__prompt__, message)


    def out(self, result):
        ''' Prints an iControl result to stdout '''

        if result != None:
            pp = pprint.PrettyPrinter(indent=4)
            pp.pprint(result)


    def lookup(self, what):
        ''' Does a DNS lookup to fetch the FQDN and all the IPs '''

        tmp = what.split(':')
        if 1 == len(tmp): tmp.append('80')
        what = tmp[0]
        port = tmp[1]
        try:
            data = socket.gethostbyname_ex(what)
        except Exception, e:
            self.info('Can\'t resolve \'%s\': %s' % (what, e))
            sys.exit(2)
        fqdn = data[0]
        ips = data[2]
        if len(ips) > 1:
            self.info('\'%s\' resolves to multiple ips \'%s\'' % (fqdn, ips))
            sys.exit(2)
        return (fqdn, ips[0], port)

    def __do_node(self, f5):
        ''' Do stuff concerning nodes '''

        a = self._args

        if not a.name:
            return lambda: f5().get_list()

        if a.sub == 'get':
            if a.sub2 == 'detail':
                def detail(f5):
                    d = {}
                    d['connection_limit'] = f5().get_connection_limit([a.name])
                    d['default_node_monitor'] = f5().get_default_node_monitor()
                    d['description'] = f5().get_description([a.name])
                    d['dynamic_ratio'] = f5().get_dynamic_ratio_v2([a.name])
                    d['monitor_instance'] = f5().get_monitor_instance([a.name])
                    d['monitor_rule'] = f5().get_monitor_rule([a.name])
                    d['monitor_status'] = f5().get_monitor_status([a.name])
                    d['object_status'] = f5().get_object_status([a.name])
                    d['rate_limit'] = f5().get_rate_limit([a.name])
                    d['ratio'] = f5().get_ratio([a.name])
                    d['session_status'] = f5().get_session_status([a.name])
                    return d
                return lambda: detail(f5)
            if a.sub2 == 'status':
                return lambda: f5().get_monitor_status([a.name])

        elif a.sub == 'create':
                try:
                    data = socket.gethostbyname_ex(a.name)
                except Exception, e:
                    self.info('Can\'t resolve \'%s\': %s' % (a.name, e))
                    sys.exit(2)
                fqdn, ip, _ = self.lookup(a.name)
                return lambda: f5().create([fqdn],[ip],[0])

        elif a.sub == 'delete':
                return lambda: f5().delete_node_address([a.name])


    def __do_monitor(self, f5):
        ''' Do stuff concerning monitor templates '''

        a = self._args

        if not a.name:
            return lambda: f5().get_template_list()

        if a.sub == 'get':
            monitorname = a.sub3
            if a.sub2 == 'desc':
                return lambda: f5().get_description([monitorname])
            if a.sub2 == 'state':
                return lambda: f5().get_template_state([monitorname])


    def __do_pool(self, f5):
        ''' Do stuff concerning pools '''

        a = self._args

        if not a.name:
            return lambda: f5().get_list()

        if a.sub == 'get':
            if a.sub2 == 'detail':
                def detail(f5):
                    d = {}
                    d['allow_nat_state'] = f5().get_allow_nat_state([a.name])
                    d['allow_snat_state'] = f5().get_allow_snat_state([a.name])
                    d['description'] = f5().get_description([a.name])
                    d['lb_method'] = f5().get_lb_method([a.name])
                    d['member'] = f5().get_member_v2([a.name])
                    d['object_status'] = f5().get_object_status([a.name])
                    d['profile'] = f5().get_profile([a.name])
                    return d
                return lambda: detail(f5)
            elif a.sub2 == 'lbmethod':
                return lambda: f5().get_lb_method([a.name])
            elif a.sub2 == 'members':
                return lambda: f5().get_member_v2([a.name])
            elif a.sub2 == 'monitor':
                return lambda: f5().get_monitor_instance([a.name])
            elif a.sub2 == 'status':
                return lambda: f5().get_object_status([a.name])

        elif a.sub == 'set':
            if a.sub2 == 'lbmethod':
                lbmethod = a.sub3
                return lambda: f5().set_lb_method([a.name], [lbmethod])

        elif a.sub == 'create':
                poolmembers = []
                method = a.m
                if a.sub3:
                    for x in a.sub3.split(','):
                        fqdn, ip, port = self.lookup(x)
                        pm = { 'address' : fqdn, 'port' : port }
                        poolmembers.append(pm)
                return lambda: f5().create_v2([a.name],[method],[poolmembers])

        elif a.sub == 'delete':
            return lambda: f5().delete_pool([a.name])

        elif a.sub == 'add':
            if a.sub2 == 'member':
                fqdn, _, port = self.lookup(a.sub3)
                member = [{ 'address' : fqdn, 'port' : port }]
                return lambda: f5().add_member_v2([a.name], [member])
            elif a.sub2 == 'monitor':
                monitorname = a.sub3
                rule = {
                    'type': 'MONITOR_RULE_TYPE_SINGLE',
                    'quorum': long(0),
                    'monitor_templates': [ monitorname ],
                }
                association = { 'pool_name': a.name, 'monitor_rule': rule }
                return lambda: f5().set_monitor_association([association])

        elif a.sub == 'del':
            if a.sub2 == 'member':
                fqdn, _, port = self.lookup(a.sub3)
                member = [{ 'address' : fqdn, 'port' : port }]
                return lambda: f5().remove_member_v2([a.name], [member])
            elif a.sub2 == 'monitors':
                # Removes all monitor associations, not just one
                return lambda: f5().remove_monitor_association([a.name])


    def __do_vserver(self, f5):
        ''' Do stuff concerning virtual servers '''

        a = self._args

        if not a.name:
            return lambda: f5().get_list()

        # Check for Pattern like /partition/foo-bar.example.com_443
        m = re.match('^(.*)_(\d+)$', a.name)
        if m:
          fqdn = m.group(1)
          port = m.group(2)
          _, ip, _ = self.lookup(fqdn)
        else:
          fqdn, ip, port = self.lookup(a.name)

        name = fqdn + '_' + port

        if a.sub == 'get':
            if a.sub2 == 'detail':
                def detail(f5):
                    d = {}
                    d['actual_hardware_acceleration'] = f5().get_actual_hardware_acceleration([name])
                    d['auto_lasthop'] = f5().get_auto_lasthop([name])
                    d['bw_controller_policy'] = f5().get_bw_controller_policy([name])
                    d['clone_pool'] = f5().get_clone_pool([name])
                    d['connection_limit'] = f5().get_connection_limit([name])
                    d['default_pool_name'] = f5().get_default_pool_name([name])
                    d['description'] = f5().get_description([name])
                    d['destination'] = f5().get_destination_v2([name])
                    d['enabled_state'] = f5().get_enabled_state([name])
                    d['fallback_persistence_profile'] = f5().get_fallback_persistence_profile([name])
                    d['gtm_score'] = f5().get_gtm_score([name])
                    d['last_hop_pool'] = f5().get_last_hop_pool([name])
                    d['object_status'] = f5().get_object_status([name])
                    d['persistence_profile'] = f5().get_persistence_profile([name])
                    d['profile'] = f5().get_profile([name])
                    d['protocol'] = f5().get_protocol([name])
                    d['rule'] = f5().get_rule([name])
                    d['snat_pool'] = f5().get_snat_pool([name])
                    d['snat_type'] = f5().get_snat_type([name])
                    d['source_address'] = f5().get_source_address([name])
                    d['source_address_translation_lsn_pool'] = f5().get_source_address_translation_lsn_pool([name])
                    d['source_address_translation_snat_pool'] = f5().get_source_address_translation_snat_pool([name])
                    d['source_address_translation_type'] = f5().get_source_address_translation_type([name])
                    d['source_port_behavior'] = f5().get_source_port_behavior([name])
                    d['translate_address_state'] = f5().get_translate_address_state([name])
                    d['translate_port_state'] = f5().get_translate_port_state([name])
                    d['type'] = f5().get_type([name])
                    d['vlan'] = f5().get_vlan([name])
                    return d
                return lambda: detail(f5)
            elif a.sub2 == 'brief':
                def brief(f5):
                    d = {}
                    d['actual_hardware_acceleration'] = f5().get_actual_hardware_acceleration([name])
                    d['default_pool_name'] = f5().get_default_pool_name([name])
                    d['destination'] = f5().get_destination_v2([name])
                    d['enabled_state'] = f5().get_enabled_state([name])
                    d['object_status'] = f5().get_object_status([name])
                    d['persistence_profile'] = f5().get_persistence_profile([name])
                    d['profile'] = f5().get_profile([name])
                    d['protocol'] = f5().get_protocol([name])
                    d['translate_address_state'] = f5().get_translate_address_state([name])
                    d['translate_port_state'] = f5().get_translate_port_state([name])
                    d['type'] = f5().get_type([name])
                    return d
                return lambda: brief(f5)
            elif a.sub2 == 'status':
                return lambda: f5().get_object_status([name])

        elif a.sub == 'create':
            protocol = a.sub2 if a.sub2 else 'PROTOCOL_TCP'
            if a.sub3:
                profile = a.sub3
            elif protocol == 'PROTOCOL_UDP':
                profile = 'udp'
            else:
                profile = 'tcp'
            poolname = a.sub4
            netmask = a.sub5 if a.sub5 else '255.255.255.255'
            vserver = {
                'name': name,
                'address': ip,
                'port': port,
                'protocol': protocol,
            }
            resource = { 'type': 'RESOURCE_TYPE_POOL' }
            if poolname: resource['default_pool_name'] = poolname
            profile = {
                    'profile_context': 'PROFILE_CONTEXT_TYPE_ALL',
                    'profile_name': profile,
            }
            self.info("vserver:%s netmask:%s resource:%s, profile:%s"
                    % (vserver, netmask, resource, profile))
            def vserver_create():
                f5().create([vserver], [netmask], [resource], [[profile]])
                # Auto disable NAT and PAT if nPath
                if profile['profile_name'] == 'nPath':
                    f5().set_translate_address_state([name], ['STATE_DISABLED'])
                    f5().set_translate_port_state([name], ['STATE_DISABLED'])
            return lambda: vserver_create()

        elif a.sub == 'delete':
            return lambda: f5().delete_virtual_server([name])

        elif a.sub == 'set':
            if a.sub2 == 'pool':
                poolname = a.sub3
                return lambda: f5().set_default_pool_name([name], [poolname])
            elif a.sub2 == 'nat':
                if a.sub3 == 'disabled':
                    return lambda: f5().set_translate_address_state([name], ['STATE_DISABLED'])
                elif a.sub3 == 'enabled':
                    return lambda: f5().set_translate_address_state([name], ['STATE_ENABLED'])
            elif a.sub2 == 'pat':
                if a.sub3 == 'disabled':
                    return lambda: f5().set_translate_port_state([name], ['STATE_DISABLED'])
                elif a.sub3 == 'enabled':
                    return lambda: f5().set_translate_port_state([name], ['STATE_ENABLED'])
            elif a.sub2 == 'snat':
                if a.sub3 == 'none':
                    return lambda: f5().set_source_address_translation_none([name])



    def run(self):
        ''' Do the actual stuff.
            We are doning some lazy evaluation stuff here. The command line
            tool does not do anything with the slow F5 API until it is clear
            what to do and that there is no semantic or syntax error. '''

        a = self._args
        lazy = None

        if a.name:
          # Remove the /partition/ prefix, setting default partition after 
          # login instead
          a.name = re.sub(self._partition, '', a.name)
          a.name = re.sub('^/+', '', a.name)

        if a.what == 'node':
            lazy = self.__do_node(lambda: self._f5.LocalLB.NodeAddressV2)
        elif a.what == 'monitor':
            lazy = self.__do_monitor(lambda: self._f5.LocalLB.Monitor)
        elif a.what == 'pool':
            lazy = self.__do_pool(lambda: self._f5.LocalLB.Pool)
        elif a.what == 'vserver':
            lazy = self.__do_vserver(lambda: self._f5.LocalLB.VirtualServer)

        if isfunction(lazy):
            self.info('Doing some stuf via the API, it may take a while')
            self.__login()
            self.out(lazy())
        else:
            print_synopsis()
            sys.exit(1)



if __name__ == '__main__':
    ''' The main function, here we will have Popcorn for free! '''

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('-h', action='store_true', help='Help')
    parser.add_argument('-v', action='store_true', help='Verbose')
    parser.add_argument('-V', action='store_true', help='Print version')
    parser.add_argument('-m', action='store', help='The default lbmethod',
        default='LB_METHOD_ROUND_ROBIN')
    parser.add_argument('-C', action='store', help='Config file',
        default=expanduser('~') + '/.fapi.conf')

    parser.add_argument('what', nargs='?', help='node|pool|monitor|vserver|...')
    parser.add_argument('name', nargs='?', help='The object name to operate on')
    parser.add_argument('sub', nargs='?', help='First sub command')
    parser.add_argument('sub2', nargs='?', help='Second sub command')
    parser.add_argument('sub3', nargs='?', help='Third sub command')
    parser.add_argument('sub4', nargs='?', help='Fourth sub command')
    parser.add_argument('sub5', nargs='?', help='Fith sub command')

    args = parser.parse_args()

    if args.h:
        parser.print_help()
        print ''
        print_synopsis()
        sys.exit(0)

    if args.V:
        sys.exit(0)

    fapi = Fapi(args)

    fapi.run()

#   try: 
#       if not fapi.run():
#           fapi.info('Don\'t know what to do')
#           sys.exit(1)
#   except Exception, e:
#       fapi.info(e)
#       sys.exit(2)

# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
