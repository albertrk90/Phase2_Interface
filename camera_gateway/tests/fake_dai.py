"""Fake DepthAI module for offline tests and dry runs of camera_gateway_a.run() (Task 06).

Implements only what the gateway and the validated safeguards call. The fake device
REFUSES (and records as FORBIDDEN:<name>) any attribute outside the read-only /
IR-off allow-list, so a device write can never pass unnoticed. pipeline.start()
feeds stand-in EncodedFrames (from the given AU lists) at 20 fps on both eyes.
"""
import json
import threading
import time
import types

import camera_gateway_a as cga
import gateway_core as gc
import standin_encoder as se
from gateway_core import pc

MS = 1_000_000

class FakeQueue:
    def __init__(self):
        self.d, self.lock = [], threading.Lock()

    def push(self, m):
        with self.lock:
            self.d.append(m)

    def tryGet(self):
        with self.lock:
            return self.d.pop(0) if self.d else None


class FakeDai(types.SimpleNamespace):
    pass


def make_fake_dai(calls, AU_L, AU_R, autocal_sticks=True, ir_ack=True, device_id="19443010B14C872F00", sensor="OV9282", frames=110, bootloader="0.0.26", skip_seqs=(),
                  calib_user=None, calib_factory=None):
    BOOT = "X_LINK_BOOTLOADER"
    user = calib_user or {"cameraData": [[0, {"intrinsicMatrix": [[1, 0, 0]]}]], "batchName": "A"}
    factory = calib_factory or {"cameraData": [[0, {"intrinsicMatrix": [[1, 0, 0]]}]], "batchName": "F"}
    enc_queues = {}

    class Info:
        def __init__(self):
            self.name, self.state = "169.254.1.222", BOOT

        def getDeviceId(self):
            return device_id

    class Calib:
        def __init__(self, d):
            self.d = d

        def eepromToJson(self):
            return json.loads(json.dumps(self.d))

    class Feature:
        def __init__(self, sock):
            self.socket, self.sensorName, self.width, self.height = sock, sensor, 1280, 800
            self.configs = [types.SimpleNamespace(width=1280, height=800, minFps=1.0, maxFps=120.0, type="SensorType.MONO")]

    ALLOWED = {"getDeviceId", "getDeviceInfo", "getIrDrivers", "getConnectedCameraFeatures", "readCalibration",
               "readFactoryCalibration", "setIrLaserDotProjectorIntensity", "setIrFloodLightIntensity", "isClosed", "close"}
    ALLOWED |= set(cga.READ_ONLY_DEVICE_GETTERS)

    class Device:
        def __init__(self, info):
            calls.append("device_open")
            object.__setattr__(self, "_closed", False)

        @staticmethod
        def getAllAvailableDevices():
            return [Info()]

        def __getattribute__(self, n):
            if not n.startswith("_") and n not in ALLOWED and n != "getAllAvailableDevices":
                calls.append("FORBIDDEN:" + n)
                raise AttributeError("fake device refuses {}".format(n))
            return object.__getattribute__(self, n)

        def getDeviceId(self):
            return device_id

        def getDeviceInfo(self):
            return Info()

        def getBootloaderVersion(self):
            return bootloader

        def getProductName(self):
            return "OAK-D-PRO-POE-AF"

        def getDeviceName(self):
            return "OAK-D-PRO-POE-AF"

        def getPlatformAsString(self):
            return "RVC2"

        def getChipTemperature(self):
            return {"average": 40.0}

        def getIrDrivers(self):
            return [("LM3644", 2, 0x63)]

        def getConnectedCameraFeatures(self):
            return [Feature("CameraBoardSocket.CAM_B"), Feature("CameraBoardSocket.CAM_C")]

        def readCalibration(self):
            calls.append("read_user_calibration")
            return Calib(user)

        def readFactoryCalibration(self):
            return Calib(factory)

        def setIrLaserDotProjectorIntensity(self, v):
            calls.append("ir_dot_{}".format(v))
            return ir_ack and v == 0.0

        def setIrFloodLightIntensity(self, v):
            calls.append("ir_flood_{}".format(v))
            return ir_ack and v == 0.0

        def isClosed(self):
            return self._closed

        def close(self):
            calls.append("device_close")
            object.__setattr__(self, "_closed", True)

    class Out:
        def __init__(self, name):
            self.name = name

        def link(self, inp):
            calls.append("link_" + self.name)

        def createOutputQueue(self, maxSize, blocking):
            calls.append("queue_{}_{}_{}".format(self.name, maxSize, blocking))
            q_ = FakeQueue()
            enc_queues[self.name] = q_
            return q_

    class Camera:
        def build(self, sock, sensorResolution, sensorFps):
            calls.append("camera_build_{}_{}x{}_{}".format(sock, *sensorResolution, sensorFps))
            self.sock = sock
            return self

        def requestOutput(self, size, type, fps, enableUndistortion):
            calls.append("request_{}_{}_{}".format(self.sock, type, enableUndistortion))
            return Out("cam_" + str(self.sock))

    class StereoDepth:
        def __init__(self):
            self.left, self.right = "L", "R"
            self.rectifiedLeft, self.rectifiedRight = Out("rectifiedLeft"), Out("rectifiedRight")

        def __getattr__(self, n):
            def f(*a):
                calls.append("stereo_{}{}".format(n, a))
            return f

    class VideoEncoder:
        def build(self, src, frameRate, profile, keyframeFrequency):
            calls.append("encoder_build_{}_{}_{}_{}".format(src.name, frameRate, profile, keyframeFrequency))
            self.src, self.kf, self.fr, self.p = src, keyframeFrequency, frameRate, profile
            self.out = Out("enc_" + src.name)
            return self

        def setRateControlMode(self, m):
            calls.append("enc_rc_{}".format(m))

        def setBitrateKbps(self, k):
            self.k = k

        def setNumBFrames(self, n):
            self.b = n

        def getProfile(self):
            return self.p

        def getRateControlMode(self):
            return "CBR"

        def getBitrateKbps(self):
            return self.k

        def getKeyframeFrequency(self):
            return self.kf

        def getNumBFrames(self):
            return self.b

        def getFrameRate(self):
            return self.fr

    class Pipeline:
        class AutoCalibrationMode:
            OFF, ON_START = "OFF", "ON_START"

        def __init__(self, device):
            self.mode = "ON_START"

        def setAutoCalibrationMode(self, m):
            calls.append("autocal_set_" + m)
            if not autocal_sticks:
                self.mode = m

        def getAutoCalibrationMode(self):
            calls.append("autocal_get_" + self.mode)
            return self.mode

        def create(self, cls):
            return cls()

        def start(self):
            calls.append("pipeline_start")

            def feed():
                for k in range(frames):
                    now = pc.mono_ns()
                    if k in skip_seqs:
                        time.sleep(0.05)
                        continue
                    for eye, au_list in (("left", AU_L), ("right", AU_R)):
                        au = au_list[k % len(au_list)] if k < len(au_list) else au_list[(k % 20) + (0 if k % 20 else 0)]
                        ft = gc.inspect_au(au).first_slice_type
                        enc_queues["enc_rectified" + eye.capitalize()].push(
                            se.FakeEncodedFrame(k, now - 30 * MS - 3_000_000_000, now - 30 * MS, au, ft))
                    time.sleep(0.05)
            threading.Thread(target=feed, daemon=True).start()

        def stop(self):
            calls.append("pipeline_stop")

    return FakeDai(Device=Device, Pipeline=Pipeline, XLinkDeviceState=types.SimpleNamespace(X_LINK_BOOTLOADER=BOOT),
                   CameraBoardSocket=types.SimpleNamespace(CAM_B="CameraBoardSocket.CAM_B", CAM_C="CameraBoardSocket.CAM_C"),
                   ImgFrame=types.SimpleNamespace(Type=types.SimpleNamespace(GRAY8="GRAY8")),
                   VideoEncoderProperties=types.SimpleNamespace(Profile=types.SimpleNamespace(H264_BASELINE="H264_BASELINE"),
                                                                RateControlMode=types.SimpleNamespace(CBR="CBR")),
                   node=types.SimpleNamespace(Camera=Camera, StereoDepth=StereoDepth, VideoEncoder=VideoEncoder),
                   __version__="fake"), user, factory
