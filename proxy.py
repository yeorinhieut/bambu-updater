from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import paho.mqtt.client as mqtt
import json
import ssl
import threading
import queue

app = Flask(__name__)
CORS(app)

mqtt_messages = queue.Queue()  # MQTT 메시지를 저장할 큐
shutdown_event = threading.Event()  # 종료 이벤트

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("MQTT 연결 성공")
        client.publish(userdata['topic'], json.dumps(userdata['payload']))
    else:
        print(f"MQTT 연결 실패, 코드: {rc}")

def on_publish(client, userdata, mid):
    print("펌웨어 업데이트 요청이 성공적으로 전송되었습니다.")
    client.disconnect()

def on_message(client, userdata, msg):
    message = msg.payload.decode()
    print(f"Received message: {message}")
    mqtt_messages.put(message)

def on_log(client, userdata, level, buf):
    log_message = f"log: {buf}"
    print(log_message)
    mqtt_messages.put(log_message)

@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({"message": "pong"})

@app.route('/terminate', methods=['POST'])
def terminate():
    print("Terminating proxy server.")
    shutdown_event.set()
    func = request.environ.get('werkzeug.server.shutdown')
    if func is not None:
        func()
    return jsonify({"message": "Terminating server."})

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

    # MQTT 클라이언트 설정
    client = mqtt.Client(userdata={'topic': mqtt_topic, 'payload': payload}, protocol=mqtt.MQTTv311)
    client.username_pw_set(mqtt_username, mqtt_password)
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.tls_insecure_set(True)

    client.on_connect = on_connect
    client.on_publish = on_publish
    client.on_message = on_message
    client.on_log = on_log

    # MQTT 브로커에 연결
    client.connect(mqtt_broker, mqtt_port, 60)

    # 연결 유지 및 메시지 처리 루프 시작
    client.loop_start()

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
