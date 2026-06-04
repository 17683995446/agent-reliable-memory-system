"""
Phase 36 Validation Tests - Network Modules (Stages 381-385)

Tests for:
- connector.py (Stage 381)
- protocol_handler.py (Stage 382)
- request_dispatcher.py (Stage 383)
- load_balancer.py (Stage 384)
- service_discovery.py (Stage 385)
"""

import unittest
import time

from src.network import (
    # Connector
    ConnectionState, ConnectionType, NetworkEndpoint, Connection, NetworkConnector,
    get_network_connector, reset_network_connector,
    # Protocol Handler
    ProtocolType, MessageDirection, ProtocolMessage, ParseResult, ProtocolHandler,
    get_protocol_handler, reset_protocol_handler,
    # Request Dispatcher
    RequestMethod, RequestPriority, RequestStatus, NetworkRequest, NetworkResponse,
    RequestDispatcher, get_request_dispatcher, reset_request_dispatcher,
    # Load Balancer
    LoadBalanceStrategy, BackendState, BackendServer, LoadBalancer,
    get_load_balancer, reset_load_balancer,
    # Service Discovery
    ServiceStatus, ServiceType, ServiceInstance, ServiceRegistry, ServiceDiscovery,
    get_service_discovery, reset_service_discovery
)


class TestNetworkConnector(unittest.TestCase):
    """Test NetworkConnector module (Stage 381)"""
    
    def setUp(self):
        reset_network_connector()
        self.connector = get_network_connector(mock_mode=True)
    
    def test_connect_disconnect(self):
        endpoint = NetworkEndpoint("localhost", 8080, ConnectionType.TCP, 5, 3)
        conn = self.connector.connect(endpoint)
        self.assertIsNotNone(conn)
        self.assertEqual(conn.state, ConnectionState.CONNECTED)
        result = self.connector.disconnect(conn.connection_id)
        self.assertTrue(result)
    
    def test_get_connection(self):
        endpoint = NetworkEndpoint("localhost", 8080, ConnectionType.TCP, 5, 3)
        conn = self.connector.connect(endpoint)
        fetched = self.connector.get_connection(conn.connection_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.connection_id, conn.connection_id)
    
    def test_get_all_connections(self):
        endpoint1 = NetworkEndpoint("localhost", 8080, ConnectionType.TCP, 5, 3)
        endpoint2 = NetworkEndpoint("localhost", 8081, ConnectionType.HTTP, 5, 3)
        self.connector.connect(endpoint1)
        self.connector.connect(endpoint2)
        conns = self.connector.get_all_connections()
        self.assertEqual(len(conns), 2)
    
    def test_health_check(self):
        endpoint = NetworkEndpoint("localhost", 8080, ConnectionType.TCP, 5, 3)
        conn = self.connector.connect(endpoint)
        result = self.connector.health_check(conn.connection_id)
        self.assertIsInstance(result, bool)
    
    def test_cleanup_inactive(self):
        endpoint = NetworkEndpoint("localhost", 8080, ConnectionType.TCP, 5, 3)
        self.connector.connect(endpoint)
        count = self.connector.cleanup_inactive(0)
        self.assertGreaterEqual(count, 0)
    
    def test_global_singleton(self):
        connector2 = get_network_connector()
        self.assertIs(self.connector, connector2)


class TestProtocolHandler(unittest.TestCase):
    """Test ProtocolHandler module (Stage 382)"""
    
    def setUp(self):
        reset_protocol_handler()
        self.handler = get_protocol_handler()
    
    def test_parse_json(self):
        data = b'{"key": "value"}'
        result = self.handler.parse(data, ProtocolType.JSON)
        self.assertTrue(result.success)
        self.assertEqual(result.data, {"key": "value"})
    
    def test_serialize_json(self):
        data = {"key": "value"}
        result = self.handler.serialize(data, ProtocolType.JSON)
        self.assertIsInstance(result, bytes)
        self.assertIn(b"key", result)
    
    def test_create_message(self):
        data = {"action": "test"}
        msg = self.handler.create_message(data, ProtocolType.JSON, MessageDirection.REQUEST)
        self.assertEqual(msg.protocol, ProtocolType.JSON)
        self.assertEqual(msg.direction, MessageDirection.REQUEST)
    
    def test_validate_message(self):
        msg = ProtocolMessage(
            message_id="test123",
            protocol=ProtocolType.JSON,
            direction=MessageDirection.REQUEST,
            headers={},
            payload={"test": True},
            timestamp=time.time(),
            metadata={}
        )
        self.assertTrue(self.handler.validate_message(msg))
    
    def test_get_supported_protocols(self):
        protocols = self.handler.get_supported_protocols()
        self.assertIn(ProtocolType.JSON, protocols)
        self.assertIn(ProtocolType.XML, protocols)
    
    def test_convert(self):
        data = b'{"key": "value"}'
        result = self.handler.convert(data, ProtocolType.JSON, ProtocolType.RAW_BINARY)
        self.assertTrue(result.success)
    
    def test_global_singleton(self):
        handler2 = get_protocol_handler()
        self.assertIs(self.handler, handler2)


class TestRequestDispatcher(unittest.TestCase):
    """Test RequestDispatcher module (Stage 383)"""
    
    def setUp(self):
        reset_request_dispatcher()
        self.dispatcher = get_request_dispatcher()
    
    def test_dispatch(self):
        request = NetworkRequest(
            request_id="",
            method=RequestMethod.GET,
            url="http://example.com",
            headers={},
            body=None,
            priority=RequestPriority.NORMAL,
            status=RequestStatus.PENDING,
            created_at=time.time(),
            timeout=30,
            metadata={}
        )
        request_id = self.dispatcher.dispatch(request)
        self.assertIsNotNone(request_id)
        self.assertGreater(len(request_id), 0)
    
    def test_get_status(self):
        request = NetworkRequest(
            request_id="",
            method=RequestMethod.GET,
            url="http://example.com",
            headers={},
            body=None,
            priority=RequestPriority.NORMAL,
            status=RequestStatus.PENDING,
            created_at=time.time(),
            timeout=30,
            metadata={}
        )
        request_id = self.dispatcher.dispatch(request)
        status = self.dispatcher.get_status(request_id)
        self.assertIn(status, [RequestStatus.PENDING, RequestStatus.PROCESSING, RequestStatus.COMPLETED])
    
    def test_cancel(self):
        request = NetworkRequest(
            request_id="",
            method=RequestMethod.GET,
            url="http://example.com",
            headers={},
            body=None,
            priority=RequestPriority.LOW,
            status=RequestStatus.PENDING,
            created_at=time.time(),
            timeout=30,
            metadata={}
        )
        request_id = self.dispatcher.dispatch(request)
        result = self.dispatcher.cancel(request_id)
        self.assertTrue(result)
    
    def test_register_handler(self):
        def dummy_handler(request):
            return NetworkResponse(
                request_id=request.request_id,
                status_code=200,
                headers={},
                body=b"OK",
                duration_ms=0,
                error=None
            )
        result = self.dispatcher.register_handler(RequestMethod.GET, dummy_handler)
        self.assertTrue(result)
    
    def test_rate_limit(self):
        result = self.dispatcher.set_rate_limit(10)
        self.assertTrue(result)
        stats = self.dispatcher.get_statistics()
        self.assertIn('dispatched', stats)
    
    def test_clear_queue(self):
        count = self.dispatcher.clear_queue()
        self.assertGreaterEqual(count, 0)
    
    def test_global_singleton(self):
        dispatcher2 = get_request_dispatcher()
        self.assertIs(self.dispatcher, dispatcher2)


class TestLoadBalancer(unittest.TestCase):
    """Test LoadBalancer module (Stage 384)"""
    
    def setUp(self):
        reset_load_balancer()
        self.lb = get_load_balancer()
    
    def test_add_remove_backend(self):
        result = self.lb.add_backend("s1", "localhost", 8080, 1)
        self.assertTrue(result)
        backends = self.lb.get_all_backends()
        self.assertEqual(len(backends), 1)
        result = self.lb.remove_backend("s1")
        self.assertTrue(result)
    
    def test_select_backend_round_robin(self):
        self.lb.set_strategy(LoadBalanceStrategy.ROUND_ROBIN)
        self.lb.add_backend("s1", "localhost", 8080, 1)
        self.lb.add_backend("s2", "localhost", 8081, 1)
        backend = self.lb.select_backend()
        self.assertIsNotNone(backend)
    
    def test_select_backend_random(self):
        self.lb.set_strategy(LoadBalanceStrategy.RANDOM)
        self.lb.add_backend("s1", "localhost", 8080, 1)
        backend = self.lb.select_backend()
        self.assertIsNotNone(backend)
    
    def test_update_weight(self):
        self.lb.add_backend("s1", "localhost", 8080, 1)
        result = self.lb.update_backend_weight("s1", 5)
        self.assertTrue(result)
        stats = self.lb.get_backend_stats("s1")
        self.assertEqual(stats['weight'], 5)
    
    def test_set_backend_state(self):
        self.lb.add_backend("s1", "localhost", 8080, 1)
        result = self.lb.set_backend_state("s1", BackendState.MAINTENANCE)
        self.assertTrue(result)
        healthy = self.lb.get_healthy_backends()
        self.assertEqual(len(healthy), 0)
    
    def test_mark_request(self):
        self.lb.add_backend("s1", "localhost", 8080, 1)
        self.lb.mark_request_start("s1")
        self.lb.mark_request_end("s1", True)
        stats = self.lb.get_backend_stats("s1")
        self.assertEqual(stats['total_requests'], 1)
    
    def test_get_statistics(self):
        self.lb.add_backend("s1", "localhost", 8080, 1)
        stats = self.lb.get_statistics()
        self.assertIn('total_backends', stats)
    
    def test_global_singleton(self):
        lb2 = get_load_balancer()
        self.assertIs(self.lb, lb2)


class TestServiceDiscovery(unittest.TestCase):
    """Test ServiceDiscovery module (Stage 385)"""
    
    def setUp(self):
        reset_service_discovery()
        self.sd = get_service_discovery()
    
    def test_register_unregister(self):
        instance_id = self.sd.register_service("api", ServiceType.API, "localhost", 8080)
        self.assertIsNotNone(instance_id)
        result = self.sd.unregister_service(instance_id)
        self.assertTrue(result)
    
    def test_discover(self):
        self.sd.register_service("api", ServiceType.API, "localhost", 8080)
        self.sd.register_service("api", ServiceType.API, "localhost", 8081)
        instances = self.sd.discover("api")
        self.assertEqual(len(instances), 2)
    
    def test_discover_by_type(self):
        self.sd.register_service("api", ServiceType.API, "localhost", 8080)
        self.sd.register_service("db", ServiceType.DATABASE, "localhost", 5432)
        instances = self.sd.discover_by_type(ServiceType.API)
        self.assertEqual(len(instances), 1)
    
    def test_heartbeat(self):
        instance_id = self.sd.register_service("api", ServiceType.API, "localhost", 8080)
        result = self.sd.heartbeat(instance_id)
        self.assertTrue(result)
    
    def test_health_check(self):
        instance_id = self.sd.register_service("api", ServiceType.API, "localhost", 8080)
        result = self.sd.health_check(instance_id)
        self.assertIsInstance(result, bool)
    
    def test_watch_unwatch(self):
        self.sd.register_service("api", ServiceType.API, "localhost", 8080)
        events = []
        def callback(event):
            events.append(event)
        watch_id = self.sd.watch("api", callback)
        self.assertIsNotNone(watch_id)
        result = self.sd.unwatch(watch_id)
        self.assertTrue(result)
    
    def test_get_all_services(self):
        self.sd.register_service("api", ServiceType.API, "localhost", 8080)
        services = self.sd.get_all_services()
        self.assertIn("api", services)
    
    def test_cleanup_stale(self):
        self.sd.register_service("api", ServiceType.API, "localhost", 8080)
        count = self.sd.cleanup_stale(0)
        self.assertGreaterEqual(count, 0)
    
    def test_get_statistics(self):
        self.sd.register_service("api", ServiceType.API, "localhost", 8080)
        stats = self.sd.get_statistics()
        self.assertIn('total_services', stats)
    
    def test_global_singleton(self):
        sd2 = get_service_discovery()
        self.assertIs(self.sd, sd2)


class TestDataStructures(unittest.TestCase):
    """Test all data structures and enums"""
    
    def test_connection_state_enum(self):
        self.assertEqual(len(ConnectionState), 5)
        self.assertIn(ConnectionState.CONNECTED, list(ConnectionState))
    
    def test_connection_type_enum(self):
        self.assertEqual(len(ConnectionType), 5)
        self.assertIn(ConnectionType.TCP, list(ConnectionType))
    
    def test_protocol_type_enum(self):
        self.assertEqual(len(ProtocolType), 5)
        self.assertIn(ProtocolType.JSON, list(ProtocolType))
    
    def test_message_direction_enum(self):
        self.assertEqual(len(MessageDirection), 3)
        self.assertIn(MessageDirection.REQUEST, list(MessageDirection))
    
    def test_request_method_enum(self):
        self.assertEqual(len(RequestMethod), 7)
        self.assertIn(RequestMethod.GET, list(RequestMethod))
    
    def test_request_priority_enum(self):
        self.assertEqual(len(RequestPriority), 4)
        self.assertIn(RequestPriority.HIGH, list(RequestPriority))
    
    def test_request_status_enum(self):
        self.assertEqual(len(RequestStatus), 5)
        self.assertIn(RequestStatus.COMPLETED, list(RequestStatus))
    
    def test_load_balance_strategy_enum(self):
        self.assertEqual(len(LoadBalanceStrategy), 5)
        self.assertIn(LoadBalanceStrategy.ROUND_ROBIN, list(LoadBalanceStrategy))
    
    def test_backend_state_enum(self):
        self.assertEqual(len(BackendState), 4)
        self.assertIn(BackendState.HEALTHY, list(BackendState))
    
    def test_service_status_enum(self):
        self.assertEqual(len(ServiceStatus), 4)
        self.assertIn(ServiceStatus.REGISTERED, list(ServiceStatus))
    
    def test_service_type_enum(self):
        self.assertEqual(len(ServiceType), 6)
        self.assertIn(ServiceType.API, list(ServiceType))


if __name__ == '__main__':
    unittest.main()
