import serial

class SerialHandler:
    def __init__(self, port, baudrate=9600):
        self.port = port
        self.baudrate = baudrate
        self.serial_connection = None
        self._recv_buf = b""
        self.last_error: str = ""

    def connect(self):
        self.last_error = ""
        try:
            self.serial_connection = serial.Serial(
                self.port,
                self.baudrate,
                timeout=0,        # non-blocking — never stalls the UI thread
                write_timeout=1,
            )
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
            except serial.SerialException as e:
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