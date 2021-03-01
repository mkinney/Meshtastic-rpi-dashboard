#!/usr/bin/env python3

from flask import Flask, render_template, request, send_from_directory, url_for, redirect
from flask_basicauth import BasicAuth
import requests
import json
import copy
import atexit
import time

from datetime import datetime

import paho.mqtt.client as mqtt

import meshtastic
from pubsub import pub

import configparser
config = configparser.ConfigParser()
config.read('app.conf')

from waitress import serve

oldReceivedNodes = dict()
receivedNodes = dict()
myNodeInfo = dict()

app = Flask(__name__)

app.config['BASIC_AUTH_USERNAME'] = config['AUTH']['username']
app.config['BASIC_AUTH_PASSWORD'] = config['AUTH']['password']
app.config['BASIC_AUTH_FORCE'] = True

basic_auth = BasicAuth(app)

def getNodeInfo():
    global myNodeInfo
    myNodeInfo = interface.getMyNodeInfo()
    return json.dumps(myNodeInfo)

def updateImeshMap():
    global oldReceivedNodes
    global receivedNodes
    receivedNodes = copy.deepcopy(interface.nodes)
    try:
        for node, nodeValue in receivedNodes.items():
            try:
                if node in oldReceivedNodes:
                    print(node +" - "+ nodeValue['user']['longName'] +" nodo presente")
                    print(str(nodeValue['position']['time']) +" "+ str(oldReceivedNodes[node]['position']['time']))
                    if nodeValue['position']['time'] > oldReceivedNodes[node]['position']['time']:
                        print(node +" - "+ nodeValue['user']['longName'] +" aggiornato")
                        client.publish("receivedNodes/"+node, json.dumps(nodeValue))
                else:
                    print(" nuovo nodo ricevuto: "+node +" - "+ nodeValue['user']['longName'])
                    client.publish("receivedNodes/"+node, json.dumps(nodeValue))
                    print(str(nodeValue['position']['time']))
            except Exception as e:
                print(e)       
        oldReceivedNodes = copy.deepcopy(receivedNodes)
    except Exception as e:
        print(e)

def getFloat(fnum):
    if isinstance(fnum, float):
        return "{:.4f}".format(fnum)
    else:
        return ""

def getLH(ts, default=""):
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S') if ts else default

def getNodes():
    nodesList = []
    for node, value in receivedNodes.items():
        if (node == myNodeInfo['user']['id']):
            continue
        print(value)
        if 'position' in value:
            lhTS = value['position'].get('time')
            if (lhTS is None) or (lhTS < (int(time.time())-86400)):
                continue                            
            if 'latitude' in value['position'] and 'longitude' in value['position'] and 'altitude' in value['position']:
                pos = getFloat(value['position'].get('latitude')) +"°, "+getFloat(value['position'].get('longitude')) + "°, " + str(value['position'].get('altitude'))+"m"
            else:
                pos=""
            lh = getLH(lhTS)
            batt = str(value['position'].get('batteryLevel', ""))
            batt = batt + ("%" if (batt != "") else "")
        else:
            pos = ""
            lh = ""
            batt = ""
        snr = str(value.get('snr'))
        snr = snr + (" dB" if (snr != "") else "")
        nodesList.append({"user":value['user']['longName'], "id":node, "pos":pos, "lh":lh, "batt":batt, "snr":snr})
        nodesList = sorted(nodesList, key=lambda k: k['lh'], reverse=True) 
    return(json.dumps(nodesList))



@app.route('/js/<path:path>')
def send_js(path):
    return send_from_directory('js', path)
@app.route('/css/<path:path>')
def send_css(path):
    return send_from_directory('css', path)

@app.route('/')
def index():
    getNodes()
    return render_template('index.html', nodes=getNodes(), nodeInfo=getNodeInfo())

@app.route('/getNodes')
def printNodes():
    return getNodes()

@app.route('/getNodeInfo')
def printNodeInfo():
    return getNodeInfo()

@app.route('/sendMessage', methods=['POST'])
def sendMessage():
    if request.method == 'POST':
        msg = request.form['fmsg']
        interface.sendText(msg, wantAck=True)
    return redirect(url_for('index'))

@app.route('/setNode', methods=['POST'])
def setData():
    if request.method == 'POST':
        interface.setOwner(request.form['flongName'])
        prefs = interface.radioConfig.preferences
        alt = int(request.form['faltitude'])
        lat = float(request.form['flatitude'])
        lon = float(request.form['flongitude'])
        ts = int(time.time())
        prefs.fixed_position = True
        interface.sendPosition(lat, lon, alt, ts)
        interface.writeConfig()  
    return redirect(url_for('index'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        login_user(user)

        flask.flash('Logged in successfully.')

        next = flask.request.args.get('next')
        if not is_safe_url(next):
            return flask.abort(400)

        return flask.redirect(next or flask.url_for('index'))
    return flask.render_template('login.html', form=form)


if __name__ == '__main__':
    interface = meshtastic.SerialInterface()
    
    client = mqtt.Client()
    client.username_pw_set(username="iz1kga", password="kgaTestPassw0rd")
    client.connect(config['MQTT']['host'], int(config['MQTT']['port']), int(config['MQTT']['keepalive']))
    client.loop_start()


    getNodeInfo()
    updateImeshMap()    
    pub.subscribe(updateImeshMap, "meshtastic.receive")
    atexit.register(lambda: interface.close())
    serve(app, host=config['NET']['bind'], port=config['NET']['port'])