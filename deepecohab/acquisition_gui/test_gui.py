import sys
import os
import time

import numpy as np
import serial
import datetime
import traceback
from pathlib import Path

import cv2
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel,QGridLayout,
    QListWidget, QFrame, QPushButton, QFileDialog, QHBoxLayout, QMessageBox, QLineEdit, QGroupBox,
    QListWidgetItem,QTextEdit
)
from PyQt5.QtCore import Qt, QTimer, QThread
from PyQt5.QtGui import QImage, QPixmap, QIcon
from serial.tools import list_ports
import qdarkstyle

from camera_worker import CameraWorker
from serial_worker import SerialReaderWorker


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowIcon(QIcon(r"C:\Repositories\DeepEcoHab\docs\logo.png"))

        self.output_path = None
        self.recording = False
        self.video_writer = None
        self.frame_timer = QTimer()             
        self.frame_timer.timeout.connect(self._blink_tick)
        self.frame_timer.start(500)
        self.frame_counter = 0
        self.blink_state = False
        self.arduino_serial = None
        self.serial_active = False
        self.config_sent = False
        self.eh_boards = []
        self.serial_threads = {}    # key: port name
        self.serial_workers = {}    # key: port name

        self.interactive_elems = set()

        self.setWindowTitle("DeepEcoHab Acquistion Software")
        self.resize(1700, 980)


        # Main widget and layout
        main_widget = QWidget()
        main_layout = QGridLayout(main_widget)
        main_layout.setColumnStretch(0, 1)  # left control panel
        main_layout.setColumnStretch(1, 3)  # camera panel
        main_layout.setColumnStretch(2, 0)  
        
        main_layout.setRowStretch(0, 1)  
        main_layout.setRowStretch(1, 6)  # device panels area
        main_layout.setRowStretch(2, 3)  

        # ---------------------
        # Acquisition Board Panel
        # ---------------------
        self.deh_board_panel_list = QListWidget()
        self.populate_com_ports(self.deh_board_panel_list)

        deh_board_layout = QVBoxLayout()
        deh_board_layout.addWidget(self.deh_board_panel_list)

        deh_board_panel_frame = QGroupBox("Device Panel")
        deh_board_panel_frame.setLayout(deh_board_layout)
        self.interactive_elems.add(self.deh_board_panel_list)

        # ---------------------
        # Arudino Panel
        # ---------------------
        self.arduino_panel_list = QListWidget()
        self.populate_arduino_ports(self.arduino_panel_list)

        self.dark_phase_input = QLineEdit()
        self.dark_phase_input.setPlaceholderText("12:00")
        self.interactive_elems.add(self.dark_phase_input)
        
        self.light_phase_input = QLineEdit()
        self.light_phase_input.setPlaceholderText("00:00")
        self.interactive_elems.add(self.light_phase_input)

        self.log_interval_input = QLineEdit()
        self.log_interval_input.setPlaceholderText("1")
        self.interactive_elems.add(self.log_interval_input)


        self.arduino_config_button = QPushButton("Send config to Arduino")
        self.arduino_config_button.clicked.connect(self.connect_and_configure_arduino)
        self.interactive_elems.add(self.arduino_config_button)

        arduino_layout = QVBoxLayout()
        arduino_layout.addWidget(self.arduino_panel_list)
        arduino_layout.addWidget(self.dark_phase_input)
        arduino_layout.addWidget(self.light_phase_input)
        arduino_layout.addWidget(self.log_interval_input)
        arduino_layout.addWidget(self.arduino_config_button)
        
        arduino_panel_frame = QGroupBox("Arduino Control Panel")
        arduino_panel_frame.setLayout(arduino_layout)
        self.interactive_elems.add(self.arduino_panel_list)

        # ---------------------
        # spin worker
        # ---------------------
        
        self.cam_thread = QThread()
        self.cam_worker = CameraWorker(video_dir=None, videoname="preview")   # temp
        self.cam_worker.moveToThread(self.cam_thread)
        
        self.cam_worker.frame_ready.connect(self._on_frame)
        self.cam_worker.error.connect(self._on_camera_error)
        self.cam_worker.finished.connect(self.cam_thread.quit)
        
        self.cam_thread.started.connect(self.cam_worker.start)
        self.cam_thread.start()


        # ---------------------
        # Camera panel
        # ---------------------
        self.camera_panel = QLabel()
        self.camera_panel.setFixedSize(1280, 1280)
        self.camera_panel.setAlignment(Qt.AlignCenter)
        self.camera_panel.setText("Starting camera...")



        self.browse_button = QPushButton("Set Working Directory")
        self.browse_button.clicked.connect(self.select_save_location)

        
        self.record_button = QPushButton("Start Recording")
        self.record_button.setDisabled(True)

        
        self.record_button.clicked.connect(self.toggle_recording)
        self.record_button.clicked.connect(self.connect_to_device)
        self.record_button.clicked.connect(self.start_logging_arduino)

        camera_layout = QVBoxLayout()
        camera_layout.addWidget(self.camera_panel)


        record_button_layout = QHBoxLayout()
        record_button_layout.addWidget(self.record_button)

        camera_layout.addLayout(record_button_layout)
        camera_panel_frame = QGroupBox("Camera Stream")
        camera_panel_frame.setLayout(camera_layout)

        #-------------------
        # Debug console
        #-------------------
        self.debug_console = QTextEdit()
        self.debug_console.setReadOnly(True)

        debug_box_layout = QVBoxLayout()
        debug_box_layout.setContentsMargins(0, 0, 0, 0)
        debug_box_layout.addWidget(self.debug_console)
        
        self.debug_container = QGroupBox("Debug Console")
        self.debug_container.setLayout(debug_box_layout)
        self.debug_container.setVisible(False)
        
        self.debug_button = QPushButton("Enable Debug Console")
        self.debug_button.clicked.connect(self.toggle_debug_console)

        #-------------------
        # Button_layout 
        #-------------------
        top_button_layout = QGridLayout()
        top_button_layout.addWidget(self.browse_button, 0, 0)
        top_button_layout.addWidget(self.debug_button, 0, 1)
        
        
        # ---------------------
        # Add to Grid Layout
        # ---------------------
        main_layout.addLayout(top_button_layout, 0, 0)
        main_layout.addWidget(deh_board_panel_frame, 1, 0)
        main_layout.addWidget(arduino_panel_frame, 2, 0)
        main_layout.addWidget(camera_panel_frame, 0, 1, 3, 1)
        main_layout.addWidget(self.debug_container, 0, 2, 3, 1)

        # Apply layout
        self.setCentralWidget(main_widget)
        
        for elem in self.interactive_elems:
            elem.setDisabled(True)
            
        def exception_hook(exctype, value, tb):
            text = "".join(traceback.format_exception(exctype, value, tb))
            if hasattr(self, "debug_console"):
                self.debug_console.append(text)
            else:
                print(text)
        
        
        sys.excepthook = exception_hook

    
    def connect_to_device(self):
        checked_items = []
        for i in range(self.deh_board_panel_list.count()):
            item = self.deh_board_panel_list.item(i)
            if item.checkState() == Qt.Checked:
                checked_items.append(item)

        if not checked_items:
            QMessageBox.warning(self, "No device selected", "Please select a COM device.")
            return

        for item in checked_items:
            port = item.text().split()[0]
            portname = os.path.basename(port)
            if port in self.serial_threads:
                continue  # Already connected

            csv_file = os.path.join(self.output_path, f"{portname}_rfid_log.csv")
            worker = SerialReaderWorker(port, 115200, csv_file)
            thread = QThread()
            worker.moveToThread(thread)

            thread.started.connect(worker.run)
            worker.data_received.connect(self.handle_serial_data)
            worker.error_occurred.connect(lambda msg, p=port: self.handle_serial_error(p, msg))
            worker.finished.connect(thread.quit)
            worker.finished.connect(worker.deleteLater)
            thread.finished.connect(thread.deleteLater)

            self.serial_threads[port] = thread
            self.serial_workers[port] = worker

            thread.start()

        self.serial_active = True

    def handle_serial_data(self, pc_time, channel, timestamp, rfid):
        print(f"[{pc_time}] CH{channel}: {rfid} @ {timestamp}")
        # Optional: log per device/file/UI

    def handle_serial_error(self, port, message):
        QMessageBox.critical(self, f"Serial Error ({port})", message)
        
    def disconnect_from_device(self):
        for port, worker in self.serial_workers.items():
            worker.stop()
        self.serial_threads.clear()
        self.serial_workers.clear()
        self.serial_active = False
        
    def populate_arduino_ports(self, list_widget):
        ports = list(serial.tools.list_ports.comports())
        list_widget.clear()
        for port in ports:
            if ("Arduino" in port.description or "ttyacm" in port.description.lower()):
                item = f"{port.device} - {port.description}"
                item = QListWidgetItem(item)
                item.setCheckState(Qt.Unchecked)
                list_widget.addItem(item)
                
        if not ports:
            list_widget.addItem("No Arduino detected!")
            
    def connect_and_configure_arduino(self):
        checked_item = None
        for i in range(self.arduino_panel_list.count()):
            item = self.arduino_panel_list.item(i)
            if item.checkState() == Qt.Checked:
                checked_item = item
                break

        if not checked_item:
            QMessageBox.warning(self, "No Arduino selected", "Please check an Arduino device.")
            return
        if not self.output_path:
            QMessageBox.warning(self, "No folder selected", "Please choose a folder to save Arduino data.")
            return

        log_path = os.path.join(self.output_path, "habitat_log.csv")
        config_path = os.path.join(self.output_path, "habitat_config.csv")
        
        port = checked_item.text().split()[0]
        dark_start = self.dark_phase_input.text().strip()
        light_start = self.light_phase_input.text().strip()
        interval = self.log_interval_input.text().strip()

        if not (dark_start and light_start and interval):
            QMessageBox.warning(self, "Missing Input", "Please fill in all timing fields.")
            return

        try:
            self.arduino_serial = serial.Serial(port, 9600, timeout=1)
            time.sleep(2)  # Arduino reset

            config_cmd = f"CONFIG,{dark_start},{light_start},{interval}\n"
            self.arduino_serial.write(config_cmd.encode())
            time.sleep(0.1)

            now = datetime.datetime.now()
            date_str = now.strftime("%Y-%m-%d")
            time_str = now.strftime("%H:%M:%S")
            time_cmd = f"TIME,{date_str},{time_str}\n"
            self.arduino_serial.write(time_cmd.encode())
            time.sleep(0.1)
            self.record_button.setEnabled(True)
            
            # Create CSV files.
            try:
                with open(log_path, "w") as f:
                    f.write("Date,Time,Phase,Temperature,Humidity\n")
                with open(config_path, "w") as f:
                    f.write("Light_Start,Light_End,CSV_Directory,Log_Interval_Min,Phase_Switch_Extra,Start_DateTime\n")
                    start_dt = datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S")
                    f.write(f"{light_start},{dark_start},{self.output_path},{interval},{start_dt}\n")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error creating CSV files: {e}")
                return
            
            QMessageBox.information(self, "Configured", f"Sent CONFIG and TIME to {port}")
            

        except serial.SerialException as e:
            QMessageBox.critical(self, "Serial Error", f"Failed to connect to {port}:\n{e}")
            
    def start_logging_arduino(self):

        if self.arduino_serial and self.arduino_serial.is_open:
            try:
                self.arduino_serial.write(b"START\n")
                QMessageBox.information(self, "Logging Started", "Arduino logging started.")
            except serial.SerialException as e:
                QMessageBox.critical(self, "Serial Error", f"Failed to send START:\n{e}")
        elif self.recording:
            QMessageBox.warning(self, "Not Connected", "Arduino is not connected.")


    def select_save_location(self):
        dir_path = QFileDialog.getExistingDirectory(
            self, "Select Save Location")
        if dir_path:
            self.output_path = dir_path
            
            if hasattr(self, "cam_worker"):
                self.cam_worker.video_dir = Path(self.output_path)
            
            for elem in self.interactive_elems:
                elem.setEnabled(True)
            
            if self.config_sent:
                self.record_button.setEnabled(True)
            else:
                print("Please send the config to Arduino.")

    def toggle_recording(self):
        save_video = os.path.join(self.output_path, "test_recording.mp4")
        
        if not self.recording:
            # Start recording
            if save_video is None:
                return
            if self.output_path is None:
                return
            self.recording = True
            self.record_button.setText("Stop Recording")
            # size from last preview frame
            if hasattr(self, "_last_frame_size"):
                w, h = self._last_frame_size
                self.cam_worker.start_recording(w, h)
            if self.arduino_serial and not self.arduino_serial.is_open:
                self.arduino_serial.open()
        else:
            # Stop recording
            self.cam_worker.stop_recording()
            self.video_writer = None
            self.recording = False
            self.record_button.setText("Start Recording")
            if self.video_writer:
                self.video_writer.release()
                self.video_writer = None
            if self.arduino_serial and self.arduino_serial.is_open:
                self.arduino_serial.close()
            for board in self.eh_boards:
                if board and board.is_open:
                    board.close()

    def _on_frame(self, frame: np.ndarray): 
        
        if self.video_writer is None:
            self._last_frame_size = frame.shape[:2]
            self.video_writer = True   # flag only
    
        # blink overlay
        if self.recording:
            if self.blink_state:
                cv2.circle(frame, (30,30), 10, (0,0,255), -1)
    
        rgb = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB if frame.ndim==2 else cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per = ch * w
        qtimg = QImage(rgb.data, w, h, bytes_per, QImage.Format_RGB888)
        self.camera_panel.setPixmap(QPixmap.fromImage(qtimg)
                                    .scaled(self.camera_panel.size(), Qt.KeepAspectRatio))
    
    def _on_camera_error(self, msg):
        QMessageBox.critical(self, "Camera error", msg)
    
    def _blink_tick(self):
        self.blink_state = not self.blink_state
    

    def closeEvent(self, event):
        reply = QMessageBox.question(
            self,
            "Confirm Exit",
            "Are you sure you want to close?\nIt will stop any ongoing recording.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.cam_worker.stop()
            self.cam_thread.quit()
            self.cam_thread.wait()

            if getattr(self, 'serial_active', False):
                self.serial_active = False

            if getattr(self, 'arduino_serial', None) and self.arduino_serial.is_open:
                self.arduino_serial.close()

            event.accept()
        else:
            event.ignore()

    def populate_com_ports(self, list_widget):
        """Populate the list with COM ports that do not include 'Arduino'."""
        ports = list_ports.comports()
        filtered_ports = []
        
        #possible extension for macOS
        for port in ports:
            if ("arduino" not in port.description.lower() 
                and "ttyacm" not in port.description.lower()):
                item = f"{port.device} - {port.description}"
                item = QListWidgetItem(item)
                item.setCheckState(Qt.Unchecked)
                list_widget.addItem(item)
                filtered_ports.append(item)
        if not filtered_ports:
            list_widget.addItem("No DeepEcoHab boards detected!")

    def wrap_in_frame(self, widget):
        """Utility to wrap widgets in a frame for visual clarity"""
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.addWidget(widget)    
        return frame
    
    
    def toggle_debug_console(self):
        if self.debug_container.isVisible():
            self.debug_container.hide()
            self.debug_button.setText("Enable Debug Console")
            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__
            self.centralWidget().layout().setColumnStretch(2, 0)
            self.adjustSize() 
        else:
            self.debug_container.show()
            self.debug_button.setText("Disable Debug Console")
            sys.stdout = EmittingStream(textWritten=self.debug_console.append) 
            sys.stderr = EmittingStream(textWritten=self.debug_console.append)
            self.centralWidget().layout().setColumnStretch(2, 1)
            self.adjustSize() 


            
class EmittingStream:
    def __init__(self, textWritten):
        self.textWritten = textWritten

    def write(self, text):
        if text.strip():
            self.textWritten(str(text))

    def flush(self):
        pass

if __name__ == "__main__":

    app = QApplication(sys.argv)
    dark_stylesheet = qdarkstyle.load_stylesheet_pyqt5()
    app.setStyleSheet(dark_stylesheet)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())