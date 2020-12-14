import random
import socket
import time
from _thread import *
import threading
from datetime import datetime
import json
import MatchServer

clients_lock = threading.Lock()
connected = 0
numPlayersInMatch = 3

clients = {}

def connectionLoop(sock):
   while True:
      data, addr = sock.recvfrom(1024)
      data = str(data)
      if addr in clients:
         if 'heartbeat' in data:
            clients[addr]['lastBeat'] = datetime.now()
      else:
         if 'connect' in data:
            clients[addr] = {}
            clients[addr]['lastBeat'] = datetime.now()
            clients[addr]['color'] = 0

            #--When there is a newly connected client, send a list of all the currently connected clients to the connected clients--#
            message = {"cmd": 0,"player":[]}
            for c in clients:
               #message["player"].append((c[0],c[1]))
               player = {}
               player['id'] = str(c)
               message['player'].append(player)
            #message = {"cmd": 0,"player":{"id":str(addr)}}

            m = json.dumps(message)
            for c in clients:
               sock.sendto(bytes(m,'utf8'), (c[0],c[1]))

def cleanClients(sock):
   while True:
      for c in list(clients.keys()):
         if (datetime.now() - clients[c]['lastBeat']).total_seconds() > 5:
            print('Dropped Client: ', c)
            
            #--Create message to inform all current clients about the dropped player--#
            message = {"cmd": 2,"droppedPlayer":{"id":str(c)}}
            clients_lock.acquire()
            del clients[c]
            clients_lock.release()

            #--Format message to json and send to all current clients--#
            m = json.dumps(message)
            for c in clients:
               sock.sendto(bytes(m,'utf8'), (c[0],c[1]))
            #-------------------------------------------#

      time.sleep(1)

def gameLoop(sock):
   global numPlayersInMatch
   while True:
      GameState = {"cmd": 1, "players": []}
      clients_lock.acquire()
      print ("Current clients:",clients)
      print (len(clients))
      for c in clients:
         player = {}
         clients[c]['color'] = {"R": random.random(), "G": random.random(), "B": random.random()}
         player['id'] = str(c)
         player['color'] = clients[c]['color']
         GameState['players'].append(player)
      s=json.dumps(GameState)
      print(s)
      for c in clients:
         sock.sendto(bytes(s,'utf8'), (c[0],c[1]))

      inMatchPlayers = []
      if len(clients) > 0:
         i = numPlayersInMatch
         for c in clients:
            if i > 0:
               i -= 1
               inMatchPlayers.append(c)
      
      print(inMatchPlayers)
      if len(inMatchPlayers) >= numPlayersInMatch:

         # Start match loop but using a thread so it doesn't block the loop
         start_new_thread(StartMatchLoop,(sock, inMatchPlayers, 3,))
         time.sleep(1) # Using this to make sure the loop initializes for sure

         print(len(inMatchPlayers))
         StartMessage = {"cmd": 3}
         s=json.dumps(StartMessage)

         for p in inMatchPlayers:
            sock.sendto(bytes(s,'utf8'), (p[0],p[1]))

      clients_lock.release()
      time.sleep(1)

def main():
   port = 12356
   s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
   s.bind(('', port))
   start_new_thread(gameLoop, (s,))
   start_new_thread(connectionLoop, (s,))
   start_new_thread(cleanClients,(s,))
   while True:
      time.sleep(1)

if __name__ == '__main__':
   main()
