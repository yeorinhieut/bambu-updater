from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import paho.mqtt.client as mqtt
import json
import ssl
import threading
import queue
import os
import time

app = Flask(__name__)
CORS(app)

mqtt_messages = queue.Queue()  # MQTT 메시지를 저장할 큐
shutdown_event = threading.Event()  # 종료 이벤트
mqtt_client = None  # 전역 MQTT 클라이언트

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("MQTT 연결 성공")
        client.subscribe(userdata['topic'])  # 구독 유지
    else:
        print(f"MQTT 연결 실패, 코드: {rc}")

def on_publish(client, userdata, mid):
    print("펌웨어 업데이트 요청이 성공적으로 전송되었습니다.")

def on_message(client, userdata, msg):
    message = msg.payload.decode()
    print(f"Received message: {message}")
    mqtt_messages.put(message)

def on_log(client, userdata, level, buf):
    log_message = f"log: {buf}"
    print(log_message)
    mqtt_messages.put(log_message)

def initialize_mqtt_client(mqtt_broker, mqtt_port, mqtt_username, mqtt_password, mqtt_topic):
    global mqtt_client
    if mqtt_client is None:
        mqtt_client = mqtt.Client(userdata={'topic': mqtt_topic, 'payload': None}, protocol=mqtt.MQTTv311)
        mqtt_client.username_pw_set(mqtt_username, mqtt_password)
        mqtt_client.tls_set(cert_reqs=ssl.CERT_NONE)
        mqtt_client.tls_insecure_set(True)

        mqtt_client.on_connect = on_connect
        mqtt_client.on_publish = on_publish
        mqtt_client.on_message = on_message
        mqtt_client.on_log = on_log

        mqtt_client.connect(mqtt_broker, mqtt_port, 60)
        mqtt_client.loop_start()

@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({"message": "pong"})

@app.route('/terminate', methods=['POST'])
def terminate():
    print("Terminating proxy server.")
    shutdown_event.set()
    if mqtt_client:
        mqtt_client.disconnect()
    func = request.environ.get('werkzeug.server.shutdown')
    if func is not None:
        func()
    response = jsonify({"message": "Terminating server."})
    response.status_code = 200

    # 시스템 명령어로 강제 종료를 스레딩하여 응답을 먼저 보냅니다.
    def shutdown_server():
        time.sleep(1)  # 클라이언트가 응답을 받을 시간을 줍니다.
        os._exit(0)

    threading.Thread(target=shutdown_server).start()
    return response

@app.route('/update', methods=['POST'])
def update():
    data = request.json
    printer_ip = data['printerIp']
    device_id = data['sn']
    access_code = data['accessCode']
    payload = data['payload']

    mqtt_broker = printer_ip
    mqtt_port = 8883
    mqtt_username = "bblp"
    mqtt_password = access_code
    mqtt_topic = f"device/{device_id}/request"

    # MQTT 클라이언트 초기화 (이미 초기화되어 있으면 재설정하지 않음)
    initialize_mqtt_client(mqtt_broker, mqtt_port, mqtt_username, mqtt_password, mqtt_topic)

    # 펌웨어 업데이트 요청 전송
    mqtt_client.user_data_set({'topic': mqtt_topic, 'payload': payload})
    mqtt_client.publish(mqtt_topic, json.dumps(payload))

    return jsonify({"message": "Update request sent."})

@app.route('/stream')
def stream():
    def event_stream():
        while not shutdown_event.is_set():
            message = mqtt_messages.get()
            yield f"data: {message}\n\n"

    return Response(event_stream(), content_type='text/event-stream')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=1883)
