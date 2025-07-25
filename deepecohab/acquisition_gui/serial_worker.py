import serial
from datetime import datetime
import csv
from PyQt5.QtCore import QObject, pyqtSignal

class SerialReaderWorker(QObject):
    data_received = pyqtSignal(str, int, str, str)
    error_occurred = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, port, baud_rate, csv_path):
        super().__init__()
        self.port = port
        self.baud_rate = baud_rate
        self.csv_path = csv_path
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        try:
            with serial.Serial(self.port, self.baud_rate, timeout=1) as ser, \
                 open(self.csv_path, "a", newline="") as csvfile:
                
                csv_writer = csv.writer(csvfile)
                csv_writer.writerow(["datetime", "antenna", "timestamp", "animal_id"])
                
                while self._running:
                    line = ser.readline().decode("utf-8", errors="ignore").strip()
                    try:
                        channel, timestamp, rfid = line.split('-')
                        channel = int(channel) + 1
                        assert len(timestamp) == 10
                        assert len(rfid) == 10
                        pc_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S:%f")[:-3]
                        
                        csv_writer.writerow([pc_time, channel, timestamp, rfid])
                        csvfile.flush()  # Ensure data is written immediately
                        
                        self.data_received.emit(pc_time, channel, timestamp, rfid)
                    except Exception:
                        continue  # Skip malformed lines
        except serial.SerialException as e:
            self.error_occurred.emit(str(e))
        self.finished.emit()