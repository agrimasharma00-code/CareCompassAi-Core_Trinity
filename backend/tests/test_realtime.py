from app.realtime import ConnectionManager


class FakeSocket:
    def __init__(self):
        self.messages = []

    async def send_json(self, message):
        self.messages.append(message)


def test_connections_are_partitioned_by_user_and_disconnect_removes_them():
    manager = ConnectionManager()
    patient_socket = FakeSocket()
    provider_socket = FakeSocket()
    unrelated_socket = FakeSocket()
    manager.connections[10].add(patient_socket)
    manager.connections[20].add(provider_socket)
    manager.connections[30].add(unrelated_socket)

    assert manager.connections[10] == {patient_socket}
    assert manager.connections[20] == {provider_socket}
    assert manager.connections[30] == {unrelated_socket}
    manager.disconnect(20, provider_socket)
    assert 20 not in manager.connections
    assert patient_socket.messages == provider_socket.messages == unrelated_socket.messages == []


def test_publish_from_sync_is_safe_when_no_websocket_is_connected():
    manager = ConnectionManager()
    manager.publish_from_sync([1, 2], {"type": "booking.created"})
