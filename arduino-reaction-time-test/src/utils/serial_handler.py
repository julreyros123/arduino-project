import serial

class SerialHandler:
    def __init__(self, port, baudrate=9600):
        self.port = port
        self.baudrate = baudrate
        self.serial_connection = None
        self._recv_buf = b""
        self.last_error: str = ""
        self.on_error = None   # optional callable(str) set by the UI for error callbacks

    def connect(self):
        self.last_error = ""
        try:
            # Build the Serial object without opening it first so we can clear
            # the DTR line before the port opens.  When DTR goes LOW→HIGH on
            # open it triggers the Arduino hardware reset (via the 100 nF cap on
            # the RESET pin), which re-runs setup(), blanks the LCD, plays the
            # startup beeps, and discards any in-flight state.  Setting dtr=False
            # keeps the line stable and lets the PING/HELLO handshake handle sync
            # instead.  Only USB-CDC boards (Uno, Mega, Nano) are affected; the
            # flag is harmless for any other adapter.
            self.serial_connection = serial.Serial()
            self.serial_connection.port         = self.port
            self.serial_connection.baudrate     = self.baudrate
            self.serial_connection.timeout      = 0   # non-blocking — never stalls the UI thread
            self.serial_connection.write_timeout = 1
            self.serial_connection.dtr          = False   # hold DTR low before open → no reset
            self.serial_connection.open()
            self._recv_buf = b""
        except serial.SerialException as e:
            self.last_error = str(e)
            print(f"Error connecting to serial port {self.port}: {e}")
            self.serial_connection = None

    def disconnect(self):
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()
        self._recv_buf = b""

    def send_data(self, data: str):
        if self.serial_connection and self.serial_connection.is_open:
            try:
                self.serial_connection.write(data.encode("ascii", errors="replace"))
            except (serial.SerialException, PermissionError, OSError) as e:
                self.last_error = str(e)
                # Force-close so is_connected() returns False immediately.
                try:
                    self.serial_connection.close()
                except Exception:
                    pass
                self.serial_connection = None
                self._recv_buf = b""
                msg = (
                    f"Serial write failed — COM port access denied.\n"
                    f"Close the Arduino IDE Serial Monitor (or any other program\n"
                    f"using this COM port) then reconnect.\n\nDetail: {e}"
                )
                if callable(self.on_error):
                    self.on_error(msg)
                else:
                    print(f"Serial write error: {e}")

    def receive_data(self):
        if not (self.serial_connection and self.serial_connection.is_open):
            return None
        try:
            chunk = self.serial_connection.read(256)
            if chunk:
                self._recv_buf += chunk
            if b"\n" in self._recv_buf:
                line, self._recv_buf = self._recv_buf.split(b"\n", 1)
                return line.decode("ascii", errors="replace").strip()
        except serial.SerialException:
            pass
        return None

    def is_connected(self):
        return self.serial_connection is not None and self.serial_connection.is_open