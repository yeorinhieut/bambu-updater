from flask import Flask, request, jsonify
from flask_cors import CORS
import paho.mqtt.client as mqtt
import json
import ssl
import threading
import os
import time

app = Flask(__name__)
CORS(app)

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("MQTT 연결 성공")
        client.publish(userdata['topic'], userdata['payload'])
    else:
        print(f"MQTT 연결 실패, 코드: {rc}")

def on_publish(client, userdata, mid):
    print("펌웨어 업데이트 요청이 성공적으로 전송되었습니다.")
    client.disconnect()

@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({"message": "pong"})

@app.route('/terminate', methods=['POST'])
def terminate():
    print("Terminating proxy server.")
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
    payload = data['payload']  # 이미 JSON으로 파싱된 데이터를 사용

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
    print(payload)

    client.on_connect = on_connect
    client.on_publish = on_publish

    # MQTT 브로커에 연결
    client.connect(mqtt_broker, mqtt_port, 60)

    # 연결 유지 및 메시지 처리 루프 시작
    client.loop_start()

    return jsonify({"message": "Update request sent."})




if __name__ == '__main__':
    app.run(host='0.0.0.0', port=1883)
