# Copyright (C) 2020-2023  Kevin O'Connor <kevin@koconnor.net>
# Copyright (C) 2025 arteuspw <arteus.pw>
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging, time, collections, multiprocessing, os, json, threading
import websocket
import requests
from . import bulk_sensor

FREEFALL_ACCEL = 9.80665 * 1000.
SCALE_XY = (16.0 * 2 * FREEFALL_ACCEL) / (2**13)
SCALE_Z = SCALE_XY

Accel_Measurement = collections.namedtuple(
    'Accel_Measurement', ('time', 'accel_x', 'accel_y', 'accel_z'))

class AccelQueryHelper:
    def __init__(self, printer):
        self.printer = printer
        self.is_finished = False
        print_time = printer.lookup_object('toolhead').get_last_move_time()
        self.request_start_time = self.request_end_time = print_time
        self.msgs = []
        self.samples = []

    def finish_measurements(self):
        toolhead = self.printer.lookup_object('toolhead')
        self.request_end_time = toolhead.get_last_move_time()
        toolhead.wait_moves()
        self.is_finished = True

    def handle_batch(self, msg):
        if self.is_finished:
            return False
        if len(self.msgs) >= 10000:
            return False
        self.msgs.append(msg)
        return True

    def has_valid_samples(self):
        for msg in self.msgs:
            data = msg['data']
            if not data:
                continue
            first_sample_time = data[0][0]
            last_sample_time = data[-1][0]
            if (first_sample_time > self.request_end_time
                    or last_sample_time < self.request_start_time):
                continue
            return True
        return True

    def get_samples(self):
        if not self.msgs:
            return self.samples
        total = sum([len(m['data']) for m in self.msgs])
        count = 0
        self.samples = samples = [None] * total
        for msg in self.msgs:
            for samp_time, x, y, z in msg['data']:
                samples[count] = Accel_Measurement(samp_time, x, y, z)
                count += 1
        del samples[count:]
        return self.samples

    def write_to_file(self, filename):
        def write_impl():
            try:
                os.nice(20)
            except:
                pass
            f = open(filename, "w")
            f.write("#time,accel_x,accel_y,accel_z\n")
            samples = self.samples or self.get_samples()
            for t, accel_x, accel_y, accel_z in samples:
                f.write("%.6f,%.6f,%.6f,%.6f\n" % (
                    t, accel_x, accel_y, accel_z))
            f.close()
        write_proc = multiprocessing.Process(target=write_impl)
        write_proc.daemon = True
        write_proc.start()

class AccelCommandHelper:
    def __init__(self, config, chip):
        self.printer = config.get_printer()
        self.chip = chip
        self.bg_client = None
        name_parts = config.get_name().split()
        self.base_name = name_parts[0]
        self.name = name_parts[-1]
        self.register_commands(self.name)
        if len(name_parts) == 1:
            if self.name == "wadxl" or not config.has_section("wadxl"):
                self.register_commands(None)

    def register_commands(self, name):
        gcode = self.printer.lookup_object('gcode')
        gcode.register_mux_command("WADXL_MEASURE", "CHIP", name,
                                   self.cmd_ACCELEROMETER_MEASURE,
                                   desc=self.cmd_ACCELEROMETER_MEASURE_help)
        gcode.register_mux_command("WADXL_QUERY", "CHIP", name,
                                   self.cmd_ACCELEROMETER_QUERY,
                                   desc=self.cmd_ACCELEROMETER_QUERY_help)
        gcode.register_mux_command("WADXL_DEBUG_READ", "CHIP", name,
                                   self.cmd_ACCELEROMETER_DEBUG_READ,
                                   desc=self.cmd_ACCELEROMETER_DEBUG_READ_help)
        gcode.register_mux_command("WADXL_DEBUG_WRITE", "CHIP", name,
                                   self.cmd_ACCELEROMETER_DEBUG_WRITE,
                                   desc=self.cmd_ACCELEROMETER_DEBUG_WRITE_help)

    cmd_ACCELEROMETER_MEASURE_help = "Start/stop accelerometer"
    def cmd_ACCELEROMETER_MEASURE(self, gcmd):
        if self.bg_client is None:
            self.bg_client = self.chip.start_internal_client()
            gcmd.respond_info("accelerometer measurements started")
            return
        name = gcmd.get("NAME", time.strftime("%Y%m%d_%H%M%S"))
        if not name.replace('-', '').replace('_', '').isalnum():
            raise gcmd.error("Invalid NAME parameter")
        bg_client = self.bg_client
        self.bg_client = None
        bg_client.finish_measurements()
        if self.base_name == self.name:
            filename = "/tmp/%s-%s.csv" % (self.base_name, name)
        else:
            filename = "/tmp/%s-%s-%s.csv" % (self.base_name, self.name, name)
        bg_client.write_to_file(filename)
        gcmd.respond_info("Writing raw accelerometer data to %s file"
                          % (filename,))

    cmd_ACCELEROMETER_QUERY_help = "Query accelerometer for the current values"
    def cmd_ACCELEROMETER_QUERY(self, gcmd):
        aclient = self.chip.start_internal_client()
        self.printer.lookup_object('toolhead').dwell(1.)
        aclient.finish_measurements()
        values = aclient.get_samples()
        if not values:
            raise gcmd.error("No accelerometer measurements found")
        _, accel_x, accel_y, accel_z = values[-1]
        gcmd.respond_info("accelerometer values (x, y, z): %.6f, %.6f, %.6f"
                          % (accel_x, accel_y, accel_z))

    cmd_ACCELEROMETER_DEBUG_READ_help = "Query register (for debugging)"
    def cmd_ACCELEROMETER_DEBUG_READ(self, gcmd):

        reg = gcmd.get("REG", minval=0, maxval=127, parser=lambda x: int(x, 0))
        gcmd.respond_info("Wireless ADXL345 - Register reading not supported")

    cmd_ACCELEROMETER_DEBUG_WRITE_help = "Set register (for debugging)"
    def cmd_ACCELEROMETER_DEBUG_WRITE(self, gcmd):
        gcmd.respond_info("Wireless ADXL345 - Register writing not supported")

def read_axes_map(config, scale_x, scale_y, scale_z):
    am = {'x': (0, scale_x), 'y': (1, scale_y), 'z': (2, scale_z),
          '-x': (0, -scale_x), '-y': (1, -scale_y), '-z': (2, -scale_z)}
    axes_map = config.getlist('axes_map', ('x','y','z'), count=3)
    if any([a not in am for a in axes_map]):
        raise config.error("Invalid axes_map parameter")
    return [am[a.strip()] for a in axes_map]

BATCH_UPDATES = 0.100

class WirelessADXL345:
    def __init__(self, config):
        self.printer = config.get_printer()
        AccelCommandHelper(config, self)
        self.axes_map = read_axes_map(config, SCALE_XY, SCALE_XY, SCALE_Z)
        self.ip = config.get('ip', 'wadxl.local')
        self.ws = None
        self.ws_thread = None
        self.is_connected = False
        self.data_buffer = []
        self.data_lock = threading.Lock()
        self.last_error_count = 0

        self.name = config.get_name().split()[-1]
        hdr = ('time', 'x_acceleration', 'y_acceleration', 'z_acceleration')

        self.batch_bulk = bulk_sensor.BatchBulkHelper(
            self.printer, self._process_batch,
            self._start_measurements, self._finish_measurements, BATCH_UPDATES)
        self.batch_bulk.add_mux_endpoint("adxl345/dump_adxl345", "sensor",
                                         self.name, {'header': hdr})



    def _connect_websocket(self):
        """Connect to WADXL"""
        try:
            ws_url = f"ws://{self.ip}:81/"
            self.ws = websocket.WebSocketApp(
                ws_url,
                on_message=self._on_ws_message,
                on_error=self._on_ws_error,
                on_close=self._on_ws_close,
                on_open=self._on_ws_open
            )
            self.ws_thread = threading.Thread(target=self.ws.run_forever)
            self.ws_thread.daemon = True
            self.ws_thread.start()

            timeout = 15.0
            start_time = time.time()
            while not self.is_connected and (time.time() - start_time) < timeout:
                time.sleep(0.1)

            if not self.is_connected:
                logging.error("Couldn't connect to WS")

        except Exception as e:
            logging.error("WebSocket connection failed: %s", str(e))
            raise

    def _on_ws_open(self, ws):
        """WebSocket connection opened"""
        self.is_connected = True
        logging.info("WebSocket connected")

    def _on_ws_close(self, ws, close_status_code, close_msg):
        """WebSocket connection closed"""
        self.is_connected = False
        logging.info("WebSocket disconnected")

    def _on_ws_error(self, ws, error):
        """WebSocket error occurred"""
        logging.error("WebSocket error: %s", str(error))
        self.last_error_count += 1

    def _on_ws_message(self, ws, message):
        """Process incoming WebSocket message"""
        try:
            lines = message.strip().split('\n')
            with self.data_lock:
                for line in lines:
                    if line and ',' in line:
                        parts = line.split(',')
                        if len(parts) >= 4:
                            timestamp = float(parts[0]) / 1000000.0
                            raw_x = int(parts[1])
                            raw_y = int(parts[2])
                            raw_z = int(parts[3])
                            self.data_buffer.append((timestamp, raw_x, raw_y, raw_z))
        except Exception as e:
            logging.error("Error parsing WebSocket data: %s", str(e))
            self.last_error_count += 1

    def _send_http_request(self, endpoint):
        """Send HTTP request to WADXL"""
        try:
            url = f"http://{self.ip}:80/{endpoint}"
            response = requests.get(url, timeout=5.0)
            return response.status_code == 200, response.text
        except Exception as e:
            logging.error("HTTP request failed: %s", str(e))
            return False, str(e)

    def start_internal_client(self):
        """Start internal client for measurements"""
        aqh = AccelQueryHelper(self.printer)
        self.batch_bulk.add_client(aqh.handle_batch)
        return aqh

    def _convert_samples(self, samples):
        """Convert raw samples to accelerometer data"""
        (x_pos, x_scale), (y_pos, y_scale), (z_pos, z_scale) = self.axes_map
        count = 0

        for ptime, raw_x, raw_y, raw_z in samples:
            raw_xyz = (raw_x, raw_y, raw_z)
            x = round(raw_xyz[x_pos] * x_scale, 6)
            y = round(raw_xyz[y_pos] * y_scale, 6)
            z = round(raw_xyz[z_pos] * z_scale, 6)
            samples[count] = (round(ptime, 6), x, y, z)
            count += 1
        del samples[count:]

    def _start_measurements(self):
        """Start measurement process"""
        logging.info("Starting measurements")

        self._connect_websocket()

        success, response = self._send_http_request("start")
        if not success:
            raise self.printer.command_error(
                "Failed to start sampling: %s" % response)

        with self.data_lock:
            self.data_buffer.clear()

        self.last_error_count = 0
        logging.info("Measurements started")

    def _finish_measurements(self):
        """Finish measurement process"""
        logging.info("Finishing measurements")

        success, response = self._send_http_request("end")
        if not success:
            logging.error("Failed to stop sampling: %s", response)

        if self.ws:
            self.ws.close()
            self.is_connected = False

        if self.ws_thread and self.ws_thread.is_alive():
            self.ws_thread.join(timeout=2.0)

        logging.info("Measurements finished")

    def _process_batch(self, eventtime):
        """Process batch of samples"""
        samples = []

        with self.data_lock:
            if self.data_buffer:
                samples = list(self.data_buffer)
                self.data_buffer.clear()

        if not samples:
            return {}

        self._convert_samples(samples)

        return {'data': samples, 'errors': self.last_error_count, 'overflows': 0}

    def read_reg(self, reg):
        """Read register - not supported in wireless mode"""
        logging.warning("Register read not supported in wireless mode")
        return 0

    def set_reg(self, reg, val, minclock=0):
        """Set register - not supported in wireless mode"""
        logging.warning("Register write not supported in wireless mode")

def load_config(config):
    return WirelessADXL345(config)

def load_config_prefix(config):
    return WirelessADXL345(config)