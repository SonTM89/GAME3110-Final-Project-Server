import random
import socket
import time
from _thread import *
import threading
from datetime import datetime
import json
import requests

players = {}
players_lock = threading.Lock()

heartbeats = {}
gameState = {}

################################################ Checking Players' Connections

# For waiting for players to enter room
# and to check for connection drops
def ConnectionLoop(sock, playersInMatch):
	gameState['beginRoundRollcall'] = 0

	while gameState['state'] != 'finish':
		data, addr = sock.recvfrom(1024)
		try:
			data = json.loads(data)
			# Who sent it
			userid = data['uid']

			if 'command' in data:

				if data['command'] == 'connect':
		
					if ConfirmPlayerHasConnected(userid, playersInMatch):
						CreatePlayerGameData(addr, userid, sock, playersInMatch)

				elif data['command'] == 'heartbeat':
					heartbeats[userid] = datetime.now();

				elif data['command'] == 'gameUpdate':
					# Json format: { 'command': '', 'uid': '', 'orderid': 0, 'state': '', 'letterGuess': '', 'solveGuess': '', 'roundScore': 0, 'cumulativeScore': 0}

					PlayerGameDataUpdate(data, userid, sock)

				# Puzzle solved, start next round
				elif data['command'] == 'roundEnd':
					print("Round End")
					HandleRoundEnd(sock);

				# If someone leaves match, still treat it as a dropped player
				elif data['command'] == 'quit':
					SendRemovePlayer(sock, userid)
					print(0)

				# Just pass the message on to everyone else
				elif data['command'] == 'loseTurn':
					print("Lose Turn")
					PassTurn(sock, data)

			if (gameState['roundsLeft'] <= 0 and gameState['state'] == "playing"):
				# Need the client to send final updates
				gameState['state'] = "gameOver"
				start_new_thread(PostGameDelay,(sock,))

		except:
			pass

######################################################### Connection Functions

def ConfirmPlayerHasConnected(userid, playersInMatch):

	# Check if player is registered in the match
	if userid not in players:
		return True

	return False

def cleanClients(sock):
	while gameState['state'] != 'finish':
		if (gameState['state'] == "gameOver" or gameState['state'] == "postmatch"):
			return

		# use for outside of loop
		playerToRemove = ''
		playerToRemoveId = -1

		for player in heartbeats.keys():
			playerToRemove = ''
			if (datetime.now() - heartbeats[player]).total_seconds() > 5:
				playerToRemove = players[player]
				playerToRemoveId = player # copy for managing clients outside of the loop

				SendRemovePlayer(sock, player)

				# Make player lose turn if they have a turn
				# Special case, if the guy that is removed is last, need to set currentPlayer to an existing index
				# Other indices will be handled on the client end
				if (len(players) >= 1 and playerToRemove['orderid'] == gameState['currentPlayer']):
					if (playerToRemove['orderid'] >= len(players) - 1):
						gameState['currentPlayer'] = 0

						passTurnMsg = {}
						passTurnMsg['currentPlayer'] = gameState['currentPlayer']

						try:
							PassTurn(sock, passTurnMsg)
						except:
							pass

				break

		# Need to remove player from heartbeat check but doing it inside the loop causes a dict size change error
		# so doing it outside of the loop and initializing the variables outside of the loop
		if (playerToRemove != ''):
			heartbeats.pop(playerToRemoveId)

		time.sleep(5)

def CheckContinue(sock):
	# Not enought people to continue
	if (len(players) <= 1 and gameState['state'] != 'finish'):
		MatchOver(sock)
		time.sleep(1)
		#sock.close()
		gameState['state'] = 'finish'

# When rounds all finish
def MatchOver(sock):
	for player in players.values():
		endMsg = {}
		endMsg['command'] = 'matchOver'
		address = player['addr']
		msg = json.dumps(endMsg)
		
		sock.sendto(bytes(msg, 'utf8'), address)

def PostGameDelay(sock):
	print("Waiting for last minute messages")
	time.sleep(5)
	print("Finished waiting")

	print("Closing match")
	ProcessResults()
	#sock.close()
	gameState['state'] = 'finish'

def ProcessResults():
	scores = []
	# Find highest score
	for player in players.values():
		scores.append(player['cumulativeScore'])

	maxScore = max(scores)
	minScore = min(scores)

	# Send results if valid game
	if (len(players) > 1):
		
		for player in players.values():
			addedWins = 0
			addedExp = 0

			totalScore = player['cumulativeScore']

			if (totalScore >= maxScore):
				addedWins = 1
				addedExp = 6

			elif (totalScore > minScore):
				addedExp = 4

			elif (totalScore == minScore):
				addedExp = 2

			SetAccountInformation(player['uid'], addedWins, addedExp)

	print(scores)

# Lambda Function for setting Account Information
def SetAccountInformation(enteredUsername, addedWins, addedExp):
    # Get existing wins/exp
    resp = requests.get("https://zkh251iic9.execute-api.us-east-1.amazonaws.com/default/GetAccount?username=" + enteredUsername)
    respBody = json.loads(resp.content)
    existingWins = respBody['numWins']
    existingExp = respBody['exp']

    # Convert string to int, may be better to return a different type through the lambda function...
    existingWins = int(existingWins)
    existingExp = int(existingExp)

    baseUrl = "https://41afs1awpk.execute-api.us-east-1.amazonaws.com/default/SetAccount"
    endpoint = "?username=" + enteredUsername + "&nwins=" + str(existingWins + addedWins) + "&xp=" + str(existingExp + addedExp)
    resp = requests.get(baseUrl + endpoint) # Maybe something other than get would be better here...

    print('Account information updated')

############################################### Match Functions

def CreatePlayerGameData(addr, userid, sock, playersInMatch):
	players_lock.acquire()
	gameData = {}

	gameData['uid'] = userid # For client reference
	gameData['addr'] = addr

	gameData['orderid'] = len(players) # Turn order will be time players join match
	gameData['state'] = ''
	gameData['letterGuess'] = ''
	gameData['solveGuess'] = ''
	gameData['spinPoints'] = 0
	gameData['roundScore'] = 0
	gameData['cumulativeScore'] = 0
	gameData['wordIndex'] = gameState['currentWord']
	gameData['currentPlayer'] = gameState['currentPlayer']

	heartbeats[userid] = datetime.now()

	players[userid] = gameData
	players_lock.release()

	# Send new player data to other clients
	for player in players.values():
		newPlayerMsg = {}
		newPlayerMsg = player.copy()
		newPlayerMsg['command'] = 'newPlayer'

		for playerAddress in players.values():
			print("Sent")
			print(newPlayerMsg)
			address = playerAddress['addr']
			msg = json.dumps(newPlayerMsg)
		
			sock.sendto(bytes(msg, 'utf8'), address)

	if (len(players) == len(playersInMatch)):
		for player in players.values():
			address = player['addr']

			# Signal Player to begin game
			StartGameSignal(sock, address)

		print("Players in match: ")
		print(players)

def PlayerGameDataUpdate(data, userid, sock):

	players[userid]['orderid'] = data['orderid']
	players[userid]['state'] = data['state']
	players[userid]['letterGuess'] = data['letterGuess']
	players[userid]['solveGuess'] = data['solveGuess']
	players[userid]['spinPoints'] = data['spinPoints']
	players[userid]['roundScore'] = data['roundScore']
	players[userid]['cumulativeScore'] = data['cumulativeScore']

	ServerGameStateRelay(sock, userid)

#Pregame setup, basically who begins game, what is the word
#Should be called for each new player and after each round
def StartGameSignal(sock, addr):
	startMsg = {}
	startMsg['command'] = 'startGame'
	startMsg['wordIndex'] = gameState['currentWord']
	startMsg['currentPlayer'] = gameState['currentPlayer']

	msg = json.dumps(startMsg)
		
	sock.sendto(bytes(msg, 'utf8'), addr)

def PassTurn(sock, passTurnMsg):

	for player in players.values():
		gameState['currentPlayer'] = passTurnMsg['currentPlayer']

		passTurnMsg['command'] = 'switchTurn'
		msg = json.dumps(passTurnMsg)

		addr = player['addr']
		sock.sendto(bytes(msg, 'utf8'), addr)

def HandleRoundEnd(sock):
	# Should only accept one round end message from all clients instead of from each

	# Wait for all players to confirm round ended
	gameState['beginRoundRollcall'] += 1
	if gameState['beginRoundRollcall'] >= len(players):
		gameState['currentWord'] = random.randint(0, gameState['remaingWords']-1)
		gameState['remaingWords'] = gameState['remaingWords'] - 1

		gameState['roundsLeft'] -= 1
		print("Rounds Left: ")
		print(gameState['roundsLeft'])

		gameState['currentPlayer'] = random.randint(0, len(players) - 1)

		for player in players.values():
			StartGameSignal(sock, player['addr'])

			print(player['addr'])

		# Reset Roll
		gameState['beginRoundRollcall'] = 0

	if (gameState['roundsLeft'] <= 0):
		MatchOver(sock)

def SendRemovePlayer(sock, userid):
	playerToBeRemoved = players.pop(userid)
	print("Removed " + userid)

	removePlayerMsg = {}
	removePlayerMsg['command'] = "playerDropped"
	removePlayerMsg['orderid'] = playerToBeRemoved['orderid']
	msg = json.dumps(removePlayerMsg)

	# Tell the others to remove the player
	for player in players.values():

		addr = player['addr']
		sock.sendto(bytes(msg, 'utf8'), addr)

	CheckContinue(sock)

################################################ Server Messaging

def ServerGameStateRelay(sock, userid):
	#while True:

	for player in players.values():
		gameStateMsg = player.copy()
		gameStateMsg["command"] = "update"
		gameStateMsg = json.dumps(gameStateMsg)

		for playerAddress in players.values():
			address = playerAddress['addr']
			try:
				sock.sendto(bytes(gameStateMsg, 'utf8'), address)
			except:
				pass

		#print("Sent ")
		#print(gameStateMsg)

################################################ Start Match

def StartMatchLoop(playersJoining, rounds):
	sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	sock.bind(('', 12345))
	print("Match started")
	gameState['currentPlayer'] = 0
	gameState['remaingWords'] = 12
	gameState['roundsLeft'] = rounds
	gameState['state'] = "playing"

	# Generate random word
	gameState['currentWord'] = random.randint(0, gameState['remaingWords']-1)
	gameState['remaingWords'] = gameState['remaingWords'] - 1

	start_new_thread(ConnectionLoop,(sock,playersJoining,))
	start_new_thread(cleanClients,(sock,))

	while gameState['state'] != 'finish':
		time.sleep(1/30)

################################################ Test Code

def main():
	sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	sock.bind(('', 12345))
	playersJoining = {'Apple':{}, 'Banana':{}, 'Orange':{}}
	rounds = 3

	StartMatchLoop(sock, playersJoining, rounds)

if __name__ == '__main__':
   main()