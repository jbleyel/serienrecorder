# -*- coding: utf-8 -*-
from __future__ import print_function
import datetime
import email
import imaplib
import os
import quopri
import re
import shutil
import string
import time
from HTMLParser import HTMLParser

import SerienRecorder
from SerienRecorderHelpers import decrypt, STBHelpers
from Components.config import config
from Screens.MessageBox import MessageBox
from SerienRecorderDatabase import SRDatabase
from SerienRecorderHelpers import TimeHelpers
from SerienRecorderSeriesServer import SeriesServer
from SerienRecorderLogWriter import SRLogger
from Tools.Directories import fileExists

SERIENRECORDER_TVPLANER_HTML_FILENAME = "%sTV-Planer.html"
SERIENRECORDER_LONG_TVPLANER_HTML_FILENAME = "%sTV-Planer_%s%s%s%s%s.html"

def getEmailData():
	# extract all html parts
	def get_html(email_message_instance):
		maintype = email_message_instance.get_content_maintype()
		if maintype == 'multipart':
			for part in email_message_instance.get_payload():
				if part.get_content_type() == 'text/html':
					return part.get_payload()

	SRLogger.writeLog("\n---------' Lade TV-Planer E-Mail '---------\n", True)

	# get emails
	if len(config.plugins.serienRec.imap_server.value) == 0:
		SRLogger.writeLog("TV-Planer: imap_server nicht gesetzt", True)
		return None

	if len(config.plugins.serienRec.imap_login_hidden.value) == 0:
		SRLogger.writeLog("TV-Planer: imap_login nicht gesetzt", True)
		return None

	if len(config.plugins.serienRec.imap_password_hidden.value) == 0:
		SRLogger.writeLog("TV-Planer: imap_password nicht gesetzt", True)
		return None

	if len(config.plugins.serienRec.imap_mailbox.value) == 0:
		SRLogger.writeLog("TV-Planer: imap_mailbox nicht gesetzt", True)
		return None

	if len(config.plugins.serienRec.imap_mail_subject.value)  == 0:
		SRLogger.writeLog("TV-Planer: imap_mail_subject nicht gesetzt", True)
		return None

	if 1 > config.plugins.serienRec.imap_mail_age.value > 100:
		config.plugins.serienRec.imap_mail_age.value = 1

	try:
		if config.plugins.serienRec.imap_server_ssl.value:
			mail = imaplib.IMAP4_SSL(config.plugins.serienRec.imap_server.value, config.plugins.serienRec.imap_server_port.value)
		else:
			mail = imaplib.IMAP4(config.plugins.serienRec.imap_server.value, config.plugins.serienRec.imap_server_port.value)

	except (imaplib.IMAP4.abort, imaplib.IMAP4.error, imaplib.IMAP4.readonly) as e:
		SRLogger.writeLog("TV-Planer: Verbindung zum E-Mail Server fehlgeschlagen [%s]" % str(e), True)
		return None
	except:
		SRLogger.writeLog("TV-Planer: Verbindung zum E-Mail Server fehlgeschlagen [unbekannter Fehler]", True)
		return None

	try:
		mail.login(decrypt(STBHelpers.getmac("eth0"), config.plugins.serienRec.imap_login_hidden.value),
				   decrypt(STBHelpers.getmac("eth0"), config.plugins.serienRec.imap_password_hidden.value))
		print("[serienrecorder]: imap login ok")

	except imaplib.IMAP4.error as e:
		SRLogger.writeLog("TV-Planer: Anmeldung am Server fehlgeschlagen [%s]" % str(e), True)
		print("[serienrecorder]: imap login failed")
		return None

	try:
		mail.select(config.plugins.serienRec.imap_mailbox.value)

	except imaplib.IMAP4.error as e:
		SRLogger.writeLog("TV-Planer: Mailbox %r nicht gefunden [%s]" % (config.plugins.serienRec.imap_mailbox.value, str(e)), True)
		return None

	searchstr = TimeHelpers.getMailSearchString()
	try:
		result, data = mail.uid('search', None, searchstr)
		if result != 'OK':
			SRLogger.writeLog("TV-Planer: Fehler bei der Suche nach TV-Planer E-Mails", True)
			SRLogger.writeLog("TV-Planer: %s" % data, True)
			return None

	except imaplib.IMAP4.error as e:
		SRLogger.writeLog("TV-Planer: Keine TV-Planer Nachricht in den letzten %s Tagen [%s]" % (str(config.plugins.serienRec.imap_mail_age.value), str(e)), True)
		SRLogger.writeLog("TV-Planer: %s" % searchstr, True)
		return None

	if len(data[0]) == 0:
		SRLogger.writeLog("TV-Planer: Keine TV-Planer Nachricht in den letzten %s Tagen" % str(config.plugins.serienRec.imap_mail_age.value), True)
		SRLogger.writeLog("TV-Planer: %s" % searchstr, True)
		return None

	# get the latest email
	latest_email_uid = data[0].split()[-1]
	# fetch the email body (RFC822) for the given UID
	try:
		result, data = mail.uid('fetch', latest_email_uid, '(RFC822)')
	except Exception as e:
		SRLogger.writeLog("TV-Planer: Laden der E-Mail fehlgeschlagen [%s]" % str(e), True)
		return None

	mail.logout()
	# extract email message including headers and alternate payloads
	email_message = email.message_from_string(data[0][1])
	if len(email_message) == 0:
		SRLogger.writeLog("TV-Planer: Leere E-Mail", True)
		return None

	# get html of wunschliste
	SRLogger.writeLog("Extrahiere HTML Part der TV-Planer E-Mail.", True)
	html = get_html(email_message)
	if html is None or len(html) == 0:
		SRLogger.writeLog("TV-Planer: Leeres HTML", True)
		return None

	if config.plugins.serienRec.tvplaner.value and config.plugins.serienRec.tvplaner_backupHTML.value:
		try:
			SRLogger.writeLog("Erstelle Backup der TV-Planer E-Mail.\n")
			htmlFilePath = SERIENRECORDER_TVPLANER_HTML_FILENAME % config.plugins.serienRec.LogFilePath.value
			writeTVPlanerHTML = open(htmlFilePath, "w")
			writeTVPlanerHTML.write(html)
			writeTVPlanerHTML.close()
		except:
			SRLogger.writeLog("TV-Planer: HTML konnte nicht für die Fehlersuche gespeichert werden.", True)

	# make one line and convert characters
	html = html.replace('=\r\n', '').replace('=\n', '').replace('=\r', '').replace('\n', '').replace('\r', '')
	html = html.replace('=3D', '=')

	try:

		def getTextContentByTitle(node, titleValue, default):
			titleNodes = node.childNodes.getElementsByAttr('title', titleValue)
			if titleNodes:
				return titleNodes[0].textContent.encode('utf-8')
			else:
				return default

		def getEpisodeTitle(node):
			childNodes = node.childNodes.getElementsByTagName('a')
			if childNodes:
				return childNodes[0].textContent.encode('utf-8')
			else:
				# Movies does not a link to the episode => only country, year
				childNodes = node.childNodes.getElementsByTagName('span')
				if childNodes:
					return childNodes[0].textContent.encode('utf-8')
				else:
					return ''

		import AdvancedHTMLParser
		SRLogger.writeLog('Starte HTML Parsing der TV-Planer E-Mail.', True)
		parser = AdvancedHTMLParser.AdvancedHTMLParser()
		html = parser.unescape(html).encode('utf-8')
		parser.parseStr(html)

		# Get tables from HTML
		tables = parser.getElementsByTagName('table')

		# Initialize regular expressions
		date_regexp = re.compile('.*TV-Planer.*?den ([0-3][0-9]\.[0-1][0-9]\.20[0-9][0-9])\s.(?:\(ab (.*?) Uhr\))?')
		url_title_regexp = re.compile('.*<a href="([^\?]+)(?:\?.*)?".*><strong.*>(.*)</strong>')
		endtime_regexp = re.compile('.*bis:\s(.*)\sUhr.*')

		# Get date and time of TV-Planer
		header = tables[1].getAllChildNodes().getElementsByTagName('div')[0].textContent.encode('utf-8')
		planerDateTime = date_regexp.findall(header)[0]
		print(planerDateTime)

		# Get transmissions
		transmissions = []
		transmissionTable = tables[1].getAllChildNodes().getElementsByTagName('table')[0]
		transmissionRows = transmissionTable.childNodes
		for transmissionRow in transmissionRows:
			transmission = []
			if not transmissionRow.hasAttribute('style'):
				transmissionColumns = transmissionRow.childNodes
				# Each transmission row has three columns
				# [0]: Start time
				starttime = transmissionColumns[0].textContent.encode('utf-8')
				if starttime != 'Anzeige':
					transmission.append(starttime.replace(' Uhr', ''))
					# [1]: URL, Title, Season, Episode, Info
					transmissionColumn = transmissionColumns[1]
					# Season, Episode, Title, Episode info, End time
					episodeInfo = ['0', '00', '', '', '0.00']

					if transmissionColumn.firstChild:
						# First child is always URL + Title
						url_title = url_title_regexp.findall(transmissionColumn.firstChild.toHTML().encode('utf-8'))[0]
						transmission.extend(url_title)
					if transmissionColumn.lastChild:
						# Last element => End time (it has to be filled with a time because later on the time will be splitted)
						endtime = endtime_regexp.findall(transmissionColumn.lastChild.toHTML().encode('utf-8'))
						if endtime:
							episodeInfo[4] = endtime[0]

					divPartIndex = 0
					for transmissionPart in transmissionColumn.childNodes:
						if transmissionPart is transmissionColumn.lastChild:
							# Skip part if it the "last" part
							continue
						if transmissionPart.tagName == 'div' and divPartIndex == 0:
							# First div element => Season / Episode / Title / e.g. NEU
							episodeInfo[0] = getTextContentByTitle(transmissionPart, 'Staffel', '0')
							episodeInfo[1] = getTextContentByTitle(transmissionPart, 'Episode', '00')
							episodeInfo[2] = getEpisodeTitle(transmissionPart)
							divPartIndex += 1
						elif transmissionPart.tagName == 'div' and divPartIndex == 1:
							# Second div element => Episode info
							episodeInfo[3] = transmissionPart.textContent.encode('utf-8')

					transmission.extend(episodeInfo)
					# [2] Channel
					transmission.append(transmissionColumns[2].textContent.encode('utf-8'))
					print(transmission)
					transmissions.append(transmission)

	except Exception as e:
		SRLogger.writeLog("TV-Planer: HTML Parsing abgebrochen [%s]" % str(e), True)
		return None

	# prepare transmissions
	# [ ( seriesName, channel, start, end, season, episode, title, '0' ) ]
	# calculate start time and end time of list in E-Mail
	missingTime = False
	if len(planerDateTime) != 2:
		SRLogger.writeLog("TV-Planer: Falsches Datumsformat", True)
		return None
	(day, month, year) = planerDateTime[0].split('.')
	if not planerDateTime[1]:
		if transmissions:
			# Get time of first transmission
			(hour, minute) = transmissions[0][0].split(':')
		else:
			missingTime = True
			(hour, minute) = ('00', '00')
	else:
		(hour, minute) = planerDateTime[1].split(':')
	liststarttime_unix = TimeHelpers.getRealUnixTime(minute, hour, day, month, year)
	# generate dictionary with final transmissions
	SRLogger.writeLog("Ab dem %s %s Uhr wurden die folgenden %d Sendungen gefunden:\n" % (planerDateTime[0], planerDateTime[1], len(transmissions)))
	print("[SerienRecorder] Ab dem %s %s Uhr wurden die folgenden Sendungen gefunden:" % (planerDateTime[0], planerDateTime[1]))
	if missingTime:
		SRLogger.writeLog("In der Kopfzeile der TV-Planer E-Mail konnte keine Uhrzeit gefunden werden, bitte die angelegten Timer kontrollieren!\n")
	transmissiondict = dict()
	for starttime, url, seriesname, season, episode, titel, description, endtime, channel in transmissions:
		try:
			if url.startswith('https://www.wunschliste.de/spielfilm'):
				if not config.plugins.serienRec.tvplaner_movies.value:
					SRLogger.writeLog("' %s - Filmaufzeichnung ist deaktiviert '" % seriesname, True)
					print("' %s - Filmaufzeichnung ist deaktiviert '" % seriesname)
					continue
				transmissiontype = '[ Film ]'
			elif url.startswith('https://www.wunschliste.de/serie'):
				if not config.plugins.serienRec.tvplaner_series.value:
					SRLogger.writeLog("' %s - Serienaufzeichnung ist deaktiviert '" % seriesname, True)
					print("' %s - Serienaufzeichnung ist deaktiviert '" % seriesname)
					continue
				transmissiontype = '[ Serie ]'
			else:
				SRLogger.writeLog("' %s - Ungültige URL %r '" % (seriesname, url), True)
				print("' %s - Serienaufzeichnung ist deaktiviert '" % seriesname)
				continue

			# get fernsehserie ID from URL
			fsID = url[str.rindex(url, '/') + 1:]

			# series
			transmission = [ seriesname ]
			# channel
			channel = channel.replace(' (Pay-TV)','').replace(' (Schweiz)','').replace(' (GB)','').replace(' (Österreich)','').replace(' (USA)','').replace(' (RP)','').replace(' (F)','').strip()
			transmission += [ channel ]
			# start time
			(hour, minute) = starttime.split(':')
			transmissionstart_unix = TimeHelpers.getRealUnixTime(minute, hour, day, month, year)
			if transmissionstart_unix < liststarttime_unix:
				transmissionstart_unix = TimeHelpers.getRealUnixTimeWithDayOffset(minute, hour, day, month, year, 1)
			transmission += [ transmissionstart_unix ]
			# end time
			(hour, minute) = endtime.split('.')
			transmissionend_unix = TimeHelpers.getRealUnixTime(minute, hour, day, month, year)
			if transmissionend_unix < transmissionstart_unix:
				transmissionend_unix = TimeHelpers.getRealUnixTimeWithDayOffset(minute, hour, day, month, year, 1)
			transmission += [ transmissionend_unix ]
			# season
			if season == '':
				season = '0'
			transmission += [ season ]
			# episode
			if episode == '':
				episode = '00'
			transmission += [ episode ]
			# title
			transmission += [ quopri.decodestring(titel) ]
			# last
			transmission += [ '0' ]
			# url
			transmission += [ url ]
			# store in dictionary transmissiondict[fsID] = [ seriesname: [ transmission 0 ], [ transmission 1], .... ]
			if fsID in transmissiondict:
				transmissiondict[fsID] += [ transmission ]
			else:
				transmissiondict[fsID] = [ transmission ]
			log = "' %s - S%sE%s - %s - %s - %s - %s - %s '" % (transmission[0], str(transmission[4]).zfill(2), str(transmission[5]).zfill(2), transmission[6], transmission[1], time.strftime("%d.%m.%Y %H:%M", time.localtime(int(transmissionstart_unix))), time.strftime("%d.%m.%Y %H:%M", time.localtime(int(transmissionend_unix))), transmissiontype)
			SRLogger.writeLog(log, True)
			print("[SerienRecorder] " + log)
		except Exception as e:
			SRLogger.writeLog("TV-Planer Verarbeitung fehlgeschlagen! [%s]" % str(e), True)

	if config.plugins.serienRec.tvplaner_create_marker.value:
		print("[SerienRecorder] Create markers...")
		database = SRDatabase(SerienRecorder.serienRecDataBaseFilePath)
		for fsID in list(transmissiondict.keys()):
			print("[SerienRecorder] Check whether or not a marker exists for fsid: [%s]" % str(fsID))
			# marker isn't in database, create new marker
			# url stored in marker isn't the final one, it is corrected later
			url = transmissiondict[fsID][0][-1]
			seriesname = transmissiondict[fsID][0][0]
			marker_type = "Serien-Marker"
			try:
				boxID = None
				seriesInfo = ""
				if url.startswith('https://www.wunschliste.de/serie'):
					seriesID = SeriesServer().getIDByFSID(fsID)
					if seriesID > 0:
						url = str(seriesID)
						data = SeriesServer().getSeriesNamesAndInfoByWLID([seriesID])
						if data:
							seriesInfo = data[0]['info']
					else:
						url = None
					if config.plugins.serienRec.tvplaner_series_activeSTB.value:
						boxID = config.plugins.serienRec.BoxID.value
				elif url.startswith('https://www.wunschliste.de/spielfilm'):
					marker_type = "Temporärer Serien-Marker"
					if config.plugins.serienRec.tvplaner_movies_activeSTB.value:
						boxID = config.plugins.serienRec.BoxID.value
				else:
					url = None

				if url:
					if database.addMarker(url, seriesname, seriesInfo, fsID, boxID, 1 if url.startswith('https://www.wunschliste.de/spielfilm') else 0):
						SRLogger.writeLog("%s für '%s (%s)' wurde angelegt" % (marker_type, seriesname, seriesInfo), True)
						print("[SerienRecorder] ' %s - %s (%s) erzeugt '" % (seriesname, marker_type, seriesInfo))
			except Exception as e:
				SRLogger.writeLog("%s für '%s' konnte wegen eines Fehlers nicht angelegt werden [%s]" % (marker_type, seriesname, str(e)), True)
				print("[SerienRecorder] %s - %s konnte wegen eines Fehlers nicht angelegt werden [%s]" % (seriesname, marker_type, str(e)))
	else:
		SRLogger.writeLog("Es werden keine Serien-Marker aus der TV-Planer E-Mail erstellt.", True)


	return transmissiondict


def imaptest(session):
	import ssl

	try:
		if config.plugins.serienRec.imap_server_ssl.value:
			mail = imaplib.IMAP4_SSL(config.plugins.serienRec.imap_server.value,
									 config.plugins.serienRec.imap_server_port.value)
		else:
			mail = imaplib.IMAP4(config.plugins.serienRec.imap_server.value,
								 config.plugins.serienRec.imap_server_port.value)


	except (imaplib.IMAP4.abort, imaplib.IMAP4.error, imaplib.IMAP4.readonly, ssl.SSLError) as e:
		session.open(MessageBox, "Verbindung zum E-Mail Server fehlgeschlagen [%s]" % str(e), MessageBox.TYPE_INFO, timeout=10)
		SRLogger.writeLog("IMAP Check: Verbindung zum Server fehlgeschlagen [%s]" % str(e), True)
		return None
	except:
		import sys
		e = sys.exc_info()[0]
		session.open(MessageBox, "Verbindung zum E-Mail Server fehlgeschlagen [%s]" % str(e), MessageBox.TYPE_INFO, timeout=10)
		SRLogger.writeLog("IMAP Check: Verbindung zum E-Mail Server fehlgeschlagen [%s]" % str(e), True)
		return None


	try:
		mail.login(decrypt(STBHelpers.getmac("eth0"), config.plugins.serienRec.imap_login_hidden.value),
				   decrypt(STBHelpers.getmac("eth0"), config.plugins.serienRec.imap_password_hidden.value))

	except imaplib.IMAP4.error as e:
		session.open(MessageBox, "Anmeldung am E-Mail Server fehlgeschlagen [%s]" % str(e), MessageBox.TYPE_INFO, timeout=10)
		SRLogger.writeLog("IMAP Check: Anmeldung auf Server fehlgeschlagen [%s]" % str(e), True)
		return None

	try:
		import string

		SRLogger.writeLog("Postfächer:", True)
		result, data = mail.list('""', '*')
		if result == 'OK':
			for item in data[:]:
				x = item.split()
				mailbox = string.join(x[2:])
				SRLogger.writeLog("%s" % mailbox, True)
	except imaplib.IMAP4.error as e:
		session.open(MessageBox, "Abrufen der Postfächer vom E-Mail Server fehlgeschlagen [%s]" % str(e), MessageBox.TYPE_INFO, timeout=10)
		SRLogger.writeLog("IMAP Check: Abrufen der Postfächer fehlgeschlagen [%s]" % str(e), True)

	try:
		mail.select(config.plugins.serienRec.imap_mailbox.value)

	except imaplib.IMAP4.error as e:
		session.open(MessageBox, "Postfach [%r] nicht gefunden [%s]" % (config.plugins.serienRec.imap_mailbox.value, str(e)), MessageBox.TYPE_INFO, timeout=10)
		SRLogger.writeLog("IMAP Check: Mailbox %r nicht gefunden [%s]" % (config.plugins.serienRec.imap_mailbox.value, str(e)), True)
		mail.logout()
		return None

	searchstr = TimeHelpers.getMailSearchString()
	SRLogger.writeLog("IMAP Check: %s" % searchstr, True)
	try:
		result, data = mail.uid('search', None, searchstr)
		SRLogger.writeLog("IMAP Check: %s (%d)" % (result, len(data[0].split(' '))), True)
		if result != 'OK':
			SRLogger.writeLog("IMAP Check: %s" % data, True)

	except imaplib.IMAP4.error as e:
		session.open(MessageBox, "Fehler beim Abrufen der TV-Planer E-Mails [%s]" % str(e), MessageBox.TYPE_INFO, timeout=10)
		SRLogger.writeLog("IMAP Check: Fehler beim Abrufen der TV-Planer E-Mails [%s]" % str(e), True)
		SRLogger.writeLog("IMAP Check: %s" % mail.error.message, True)

	mail.logout()
	session.open(MessageBox, "IMAP Test abgeschlossen - siehe Log", MessageBox.TYPE_INFO, timeout=10)


def resetTVPlanerHTMLBackup():
	if config.plugins.serienRec.tvplaner.value and config.plugins.serienRec.tvplaner_backupHTML.value:
		logFile = SERIENRECORDER_TVPLANER_HTML_FILENAME % config.plugins.serienRec.LogFilePath.value

		if not config.plugins.serienRec.longLogFileName.value:
			# logFile leeren (renamed to .old)
			if fileExists(logFile):
				shutil.move(logFile, "%s.old" % logFile)
		else:
			lt = datetime.datetime.now() - datetime.timedelta(days=config.plugins.serienRec.deleteLogFilesOlderThan.value)
			for filename in os.listdir(config.plugins.serienRec.LogFilePath.value):
				if (filename.find('TV-Planer_') == 0) and (int(os.path.getmtime(os.path.join(config.plugins.serienRec.LogFilePath.value, filename))) < int(lt.strftime("%s"))):
					try:
						os.remove('%s%s' % (config.plugins.serienRec.LogFilePath.value, filename))
					except:
						SRLogger.writeLog("TV-Planer HTML Backup konnte nicht gelöscht werden: %s" % os.path.join(config.plugins.serienRec.LogFilePath.value, filename), True)

		open(logFile, 'w').close()

def backupTVPlanerHTML():
	if config.plugins.serienRec.tvplaner.value and config.plugins.serienRec.tvplaner_backupHTML.value and config.plugins.serienRec.longLogFileName.value:
		lt = time.localtime()
		logFile = SERIENRECORDER_TVPLANER_HTML_FILENAME % config.plugins.serienRec.LogFilePath.value
		logFileSave = SERIENRECORDER_LONG_TVPLANER_HTML_FILENAME % (config.plugins.serienRec.LogFilePath.value, str(lt.tm_year), str(lt.tm_mon).zfill(2), str(lt.tm_mday).zfill(2), str(lt.tm_hour).zfill(2), str(lt.tm_min).zfill(2))
		shutil.copy(logFile, logFileSave)
