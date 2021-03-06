"""
EnOcean Component.

For more details about this component, please refer to the documentation at
https://home-assistant.io/components/EnOcean/
"""
import logging

import voluptuous as vol

from homeassistant.const import CONF_DEVICE
import homeassistant.helpers.config_validation as cv

REQUIREMENTS = ['enocean-lib==1.0.0']

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'enocean'

ENOCEAN_DONGLE = None

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_DEVICE): cv.string,
    }),
}, extra=vol.ALLOW_EXTRA)


def setup(hass, config):
    """Set up the EnOcean component."""
    global ENOCEAN_DONGLE

    serial_dev = config[DOMAIN].get(CONF_DEVICE)

    ENOCEAN_DONGLE = EnOceanDongle(hass, serial_dev)

    return True


class EnOceanDongle:
    """Representation of an EnOcean dongle."""

    def __init__(self, hass, ser):
        """Initialize the EnOcean dongle."""
        from enocean.communicators.serialcommunicator import SerialCommunicator
        self.__communicator = SerialCommunicator(
            port=ser, callback=self.callback)
        self.__communicator.start()
        self.__devices = []
        self.base_id = self.__communicator.base_id

    def register_device(self, dev):
        """Register another device."""
        self.__devices.append(dev)

    def send_command(self, command):
        """Send a command from the EnOcean dongle."""
        self.__communicator.send(command)

    # pylint: disable=no-self-use
    def _combine_hex(self, data):
        """Combine list of integer values to one big integer."""
        output = 0x00
        for i, j in enumerate(reversed(data)):
            output |= (j << i * 8)
        return output

    def callback(self, temp):
        """Handle EnOcean device's callback.

        This is the callback function called by python-enocan whenever there
        is an incoming packet.
        """
        from enocean.protocol.packet import RadioPacket, Packet
        from enocean.protocol.constants import PACKET, RORG
        if isinstance(temp, RadioPacket):
            _LOGGER.debug("Received radio packet: %s", temp)
            rxtype = None
            value = None
            channel = 0
            if temp.rorg == RORG.VLD:
                temp.select_eep(0x05, 0x00)
                temp.parse_eep()
                rxtype = "cover"
                value = temp.parsed["POS"]["raw_value"]
            if temp.data[6] == 0x30:
                rxtype = "wallswitch"
                value = 1
            elif temp.data[6] == 0x20:
                rxtype = "wallswitch"
                value = 0
            elif temp.data[4] == 0x0c:
                rxtype = "power"
                value = temp.data[3] + (temp.data[2] << 8)
            elif temp.data[2] & 0x60 == 0x60:
                rxtype = "switch_status"
                channel = temp.data[2] & 0x1F
                if temp.data[3] == 0xe4:
                    value = 1
                elif temp.data[3] == 0x80:
                    value = 0
            elif temp.data[0] == 0xa5 and temp.data[1] == 0x02:
                rxtype = "dimmerstatus"
                value = temp.data[2]
            for device in self.__devices:
                if rxtype == "cover" and device.stype == "cover":
                    if temp.sender_int == self._combine_hex(device.dev_id):
                        device.value_changed(value)
                if rxtype == "wallswitch" and device.stype == "listener":
                    if temp.sender_int == self._combine_hex(device.dev_id):
                        device.value_changed(value, temp.data[1])
                if rxtype == "power" and device.stype == "powersensor":
                    if temp.sender_int == self._combine_hex(device.dev_id):
                        device.value_changed(value)
                if rxtype == "power" and device.stype == "switch":
                    if temp.sender_int == self._combine_hex(device.dev_id):
                        if value > 10:
                            device.value_changed(1)
                if rxtype == "switch_status" and device.stype == "switch" and \
                        channel == device.channel:
                    if temp.sender_int == self._combine_hex(device.dev_id):
                        device.value_changed(value)
                if rxtype == "dimmerstatus" and device.stype == "dimmer":
                    if temp.sender_int == self._combine_hex(device.dev_id):
                        device.value_changed(value)
        elif isinstance(temp, Packet):
            # case of base_id packet which not identied as
            # RadioPacket but simple Packet
            from enocean.protocol.constants import RETURN_CODE
            packet = temp
            if (packet.packet_type == PACKET.RESPONSE
                    and packet.response == RETURN_CODE.OK
                    and len(packet.response_data) == 4):
                self.__communicator.base_id = packet.response_data


class EnOceanDevice():
    """Parent class for all devices associated with the EnOcean component."""

    def __init__(self):
        """Initialize the device."""
        ENOCEAN_DONGLE.register_device(self)
        self.stype = ""
        self.sensorid = [0x00, 0x00, 0x00, 0x00]
        self.base_id = ENOCEAN_DONGLE.base_id

    # pylint: disable=no-self-use
    def send_command(self, data, optional, packet_type):
        """Send a command via the EnOcean dongle."""
        from enocean.protocol.packet import Packet
        packet = Packet(packet_type, data=data, optional=optional)
        ENOCEAN_DONGLE.send_command(packet)

    def send_packet(self, packet):
        """Send a packet via the EnOcean dongle."""
        ENOCEAN_DONGLE.send_command(packet)
