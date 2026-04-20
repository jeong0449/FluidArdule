import serial
import mido
import time

PORT = '/dev/serial/by-id/usb-Arduino__www.arduino.cc__0043_75834353930351211140-if00'

# 시리얼 열기
ser = serial.Serial(PORT, 31250, timeout=0.001)

# UNO 리셋 안정화 대기
time.sleep(2)

# ALSA seq 포트 생성
outport = mido.open_output('UNO-bridge', virtual=True)

running_status = None
data_bytes = []

def expected_data_len(status):
    if 0x80 <= status <= 0xBF:
        return 2
    if 0xC0 <= status <= 0xDF:
        return 1
    if 0xE0 <= status <= 0xEF:
        return 2
    return 0

while True:
    b = ser.read(1)
    if not b:
        continue

    byte = b[0]

    # --- REALTIME 메시지 (중간에 끼어듦) ---
    if 0xF8 <= byte <= 0xFF:
        try:
            msg = mido.Message.from_bytes([byte])
            outport.send(msg)
        except:
            pass
        continue

    # --- SYSTEM 메시지 (간단히 무시) ---
    if 0xF0 <= byte <= 0xF7:
        running_status = None
        data_bytes = []
        continue

    # --- STATUS BYTE ---
    if byte & 0x80:
        running_status = byte
        data_bytes = []
        continue

    # --- DATA BYTE ---
    if running_status is None:
        continue

    data_bytes.append(byte)
    needed = expected_data_len(running_status)

    if needed and len(data_bytes) >= needed:
        raw = [running_status] + data_bytes[:needed]

        try:
            msg = mido.Message.from_bytes(raw)

            # NOTE OFF 안정화 (velocity 0 보정)
            if msg.type == 'note_on' and msg.velocity == 0:
                msg = mido.Message('note_off',
                                   channel=msg.channel,
                                   note=msg.note,
                                   velocity=0)

            outport.send(msg)

        except Exception:
            pass

        data_bytes = data_bytes[needed:]
