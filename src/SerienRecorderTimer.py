# coding=utf-8

# This file contains the SerienRecoder Series Planner
from __future__ import print_function
import time, datetime, sys
import NavigationInstance
import SerienRecorder

from Components.config import config
from RecordTimer import RecordTimerEntry
from Screens.MessageBox import MessageBox
from ServiceReference import ServiceReference
from Tools import Notifications

from SerienRecorderLogWriter import SRLogger
from SerienRecorderDatabase import SRDatabase
from SerienRecorderHelpers import STBHelpers, TimeHelpers, getDirname

class serienRecTimer:
	def __init__(self):

		self.countTimer = 0
		self.countTimerUpdate = 0
		self.countNotActiveTimer = 0
		self.countTimerFromWishlist = 0
		self.messageList = []

		self.database = SRDatabase(SerienRecorder.serienRecDataBaseFilePath)
		self.tempDB = None
		self.konflikt = ""
		self.enableDirectoryCreation = False
		self.channelList = STBHelpers.buildSTBChannelList()

	def setTempDB(self, database):
		self.tempDB = database

	def getCounts(self):
		return self.countTimer, self.countTimerUpdate, self.countNotActiveTimer, self.countTimerFromWishlist, self.messageList

	@staticmethod
	def getTimerName(series_name, series_season, series_episode, series_title, marker_type):
		if marker_type == 1:
			timer_name = series_name
		else:
			if config.plugins.serienRec.TimerName.value == "0":
				timer_name = "%s - S%sE%s - %s" % (series_name, str(series_season).zfill(2), str(series_episode).zfill(2), series_title)
			elif config.plugins.serienRec.TimerName.value == "2":
				timer_name = "S%sE%s - %s" % (str(series_season).zfill(2), str(series_episode).zfill(2), series_title)
			elif config.plugins.serienRec.TimerName.value == "3":
				timer_name = "%s - S%sE%s" % (series_name, str(series_season).zfill(2), str(series_episode).zfill(2))
			else:
				timer_name = series_name

		return timer_name

	def activate(self):
		# versuche deaktivierte Timer zu aktivieren oder auf anderer Box zu erstellen
		from enigma import eEPGCache

		deactivatedTimers = self.database.getDeactivatedTimers()
		for deactivatedTimer in deactivatedTimers:
			(serien_name, serien_fsid, staffel, episode, serien_title, serien_time, stbRef, webChannel, eit) = deactivatedTimer
			if eit > 0:
				markerType = self.database.getMarkerType(serien_fsid)
				if markerType is None:
					# Marker type not found in database => it's a movie
					markerType = 1
				else:
					markerType = int(markerType)
				serien_wlid = self.database.getMarkerWLID(serien_fsid)
				recordHandler = NavigationInstance.instance.RecordTimer
				(dirname, dirname_serie) = getDirname(self.database, serien_name, serien_fsid, staffel)
				channelName = STBHelpers.getChannelByRef(self.channelList, stbRef)
				try:
					timerFound = False
					# suche in deaktivierten Timern
					for timer in recordHandler.processed_timers:
						if timer and timer.service_ref:
							if (timer.begin == serien_time) and (timer.eit == eit) and (
									str(timer.service_ref).lower() == stbRef.lower()):
								# versuche deaktivierten Timer zu aktivieren
								label_serie = "%s - S%sE%s - %s" % (serien_name, str(staffel).zfill(2), str(episode).zfill(2), serien_title)
								timer_name = self.getTimerName(serien_name, staffel, episode, serien_title, markerType)

								SRLogger.writeLog("Versuche deaktivierten Timer zu aktivieren: ' %s - %s '" % (serien_title, dirname))

								if STBHelpers.checkTuner(str(timer.begin), str(timer.end), str(timer.service_ref)):
									from Components.TimerSanityCheck import TimerSanityCheck
									timer.disabled = False
									timersanitycheck = TimerSanityCheck(recordHandler.timer_list, timer)
									if timersanitycheck.check():
										self.countTimerUpdate += 1
										NavigationInstance.instance.RecordTimer.timeChanged(timer)

										# Eintrag in das timer file
										self.database.activateTimer(serien_fsid, staffel, episode, serien_title,
										                            serien_time, stbRef, webChannel, eit)
										show_start = time.strftime("%d.%m.%Y - %H:%M", time.localtime(int(serien_time)))
										SRLogger.writeLog("' %s ' - Timer wurde aktiviert -> %s %s @ %s" % (
										label_serie, show_start, timer_name, channelName), True)
										timer.log(0, "[SerienRecorder] Activated timer")
									else:
										timer.disabled = True

								timerFound = True
								break

					if not timerFound:
						# suche in (manuell) aktivierten Timern
						for timer in recordHandler.timer_list:
							if timer and timer.service_ref:
								if (timer.begin == serien_time) and (timer.eit == eit) and (
										str(timer.service_ref).lower() == stbRef.lower()):
									# Eintrag in das timer file
									self.database.activateTimer(serien_fsid, staffel, episode, serien_title,
									                            serien_time, stbRef, webChannel, eit)
									timerFound = True
									break

					if not timerFound:
						# versuche deaktivierten Timer (auf anderer Box) zu erstellen
						(margin_before, margin_after) = self.database.getMargins(serien_fsid, webChannel,
						                                                         config.plugins.serienRec.margin_before.value,
						                                                         config.plugins.serienRec.margin_after.value)

						# get VPS settings for channel
						vpsSettings = self.database.getVPS(serien_fsid, webChannel)

						# get tags from marker
						tags = self.database.getTags(serien_wlid)

						# get addToDatabase for marker
						addToDatabase = self.database.getAddToDatabase(serien_wlid)

						# get autoAdjust for marker
						autoAdjust = self.database.getAutoAdjust(serien_wlid, webChannel)

						epgcache = eEPGCache.getInstance()
						allevents = epgcache.lookupEvent(['IBD', (stbRef, 2, eit, -1)]) or []

						for eventid, begin, duration in allevents:
							if int(begin) == (int(serien_time) + (int(margin_before) * 60)):
								label_serie = "%s - S%sE%s - %s" % (serien_name, str(staffel).zfill(2), str(episode).zfill(2), serien_title)
								timer_name = self.getTimerName(serien_name, staffel, episode, serien_title, markerType)
								SRLogger.writeLog("Versuche deaktivierten Timer aktiv zu erstellen: ' %s - %s '" % (serien_title, dirname))
								end_unixtime = int(begin) + int(duration)
								end_unixtime = int(end_unixtime) + (int(margin_after) * 60)
								result = serienRecBoxTimer.addTimer(stbRef, str(serien_time), str(end_unixtime),
								                                    timer_name, "S%sE%s - %s" % (
								                                    str(staffel).zfill(2), str(episode).zfill(2),
								                                    serien_title), eit, False, dirname, vpsSettings,
								                                    tags, autoAdjust, None)
								if result["result"]:
									self.countTimer += 1
									if addToDatabase:
										# Eintrag in das timer file
										self.database.activateTimer(serien_fsid, staffel, episode, serien_title,
										                            serien_time, stbRef, webChannel, eit)
									show_start = time.strftime("%d.%m.%Y - %H:%M", time.localtime(int(serien_time)))
									SRLogger.writeLog("' %s ' - Timer wurde angelegt -> %s %s @ %s" % (label_serie, show_start, timer_name, channelName), True)
								break

				except:
					pass

	def update(self, timer_list, eit, end_unixtime, new_episode, new_serien_title, new_serien_name, serien_fsid, serien_time, new_staffel, start_unixtime, stbRef, title, dirname, vpsSettings, markerType):
		timerUpdated = False
		timerFound = False
		print("[SerienRecorder] Iterate timers to update timer: " + title)
		for timer in timer_list:
			if timer and timer.service_ref:
				# skip all timer with false service ref
				print("[SerienRecorder] Get timer for update: [%s] [%s] [%s]" % (timer.name, str(timer.service_ref).lower() + " / " + str(stbRef).lower(), str(timer.begin) + " / " + str(serien_time)))
				if (str(timer.service_ref).lower() == str(stbRef).lower()) and (str(timer.begin) == str(serien_time)):
					# Timer gefunden, weil auf dem richtigen Sender und Startzeit im Timer entspricht Startzeit in SR DB
					print("[SerienRecorder] Timer found")
					timerFound = True
					# Muss der Timer aktualisiert werden?

					# Event ID
					updateEIT = False
					old_eit = timer.eit
					print("[SerienRecorder] EIT: [%s]" % str(timer.eit) + " / " + str(eit))
					if timer.eit != int(eit):
						timer.eit = eit
						# Respect VPS settings if eit is available now
						if SerienRecorder.VPSPluginAvailable and eit is not 0:
							timer.vpsplugin_enabled = vpsSettings[0]
							timer.vpsplugin_overwrite = timer.vpsplugin_enabled and (not vpsSettings[1])

						updateEIT = True

					# Startzeit
					updateStartTime = False
					print("[SerienRecorder] Start: [%s]" % str(timer.begin) + " / " + str(start_unixtime))
					if start_unixtime and timer.begin != start_unixtime and abs(start_unixtime - timer.begin) > 30:
						timer.begin = start_unixtime
						timer.end = end_unixtime
						NavigationInstance.instance.RecordTimer.timeChanged(timer)
						updateStartTime = True
					else:
						# Reset start_unixtime to timer start time to keep database and timer in sync if start time changed lesser than 30 seconds
						start_unixtime = timer.begin

					# Endzeit
					updateEndTime = False
					old_end = time.strftime("%d.%m. - %H:%M", time.localtime(int(timer.end)))
					print("[SerienRecorder] End: [%s]" % str(timer.end) + " / " + str(end_unixtime))
					if end_unixtime and timer.end != end_unixtime and abs(end_unixtime - timer.end) > 30:
						timer.begin = start_unixtime
						timer.end = end_unixtime
						NavigationInstance.instance.RecordTimer.timeChanged(timer)
						updateEndTime = True
					else:
						# Reset start_unixtime to timer start time to keep database and timer in sync if start time changed lesser than 30 seconds
						end_unixtime = timer.end

					# Timername
					updateName = False
					old_timername = timer.name
					timer_name = self.getTimerName(new_serien_name, new_staffel, new_episode, new_serien_title, markerType)
					print("[SerienRecorder] Name: [%s]" % str(timer.name) + " / " + str(timer_name))
					if timer.name != timer_name:
						timer.name = timer_name
						updateName = True

					# Timerbeschreibung
					updateDescription = False
					old_timerdescription = timer.description
					timer_description = "S%sE%s - %s" % (str(new_staffel).zfill(2), str(new_episode).zfill(2), new_serien_title)
					print("[SerienRecorder] Description: [%s]" % str(timer.description) + " / " + str(timer_description))
					if timer.description != timer_description:
						timer.description = timer_description
						updateDescription = True

					# Directory
					updateDirectory = False
					old_dirname = timer.dirname
					print("[SerienRecorder] Directory: [%s]" % str(timer.dirname) + " / " + str(dirname))
					if timer.dirname != dirname:
						(dirname, dirname_serie) = getDirname(self.database, new_serien_name, serien_fsid, new_staffel)
						STBHelpers.createDirectory(serien_fsid, 0, dirname, dirname_serie)
						timer.dirname = dirname
						updateDirectory = True

					if updateEIT or updateStartTime or updateName or updateDescription or updateDirectory:
						SRLogger.writeLog("' %s - %s '" % (title, dirname), True)
						new_start = time.strftime("%d.%m. - %H:%M", time.localtime(int(start_unixtime)))
						old_start = time.strftime("%d.%m. - %H:%M", time.localtime(int(serien_time)))
						new_end = time.strftime("%d.%m. - %H:%M", time.localtime(int(end_unixtime)))
						if updateStartTime:
							SRLogger.writeLog("   Startzeit wurde aktualisiert von %s auf %s" % (old_start, new_start), True)
							timer.log(0, "[SerienRecorder] Changed timer start from %s to %s" % (old_start, new_start))
						if updateEndTime:
							SRLogger.writeLog("   Endzeit wurde aktualisiert von %s auf %s" % (old_end, new_end), True)
							timer.log(0, "[SerienRecorder] Changed timer end from %s to %s" % (old_end, new_end))
						if updateEIT:
							SRLogger.writeLog("   Event ID wurde aktualisiert von %s auf %s" % (str(old_eit), str(eit)), True)
							timer.log(0, "[SerienRecorder] Changed event ID from %s to %s" % (str(old_eit), str(eit)))
						if updateName:
							SRLogger.writeLog("   Name wurde aktualisiert von %s auf %s" % (old_timername, timer_name), True)
							timer.log(0, "[SerienRecorder] Changed name from %s to %s" % (old_timername, timer_name))
						if updateDescription:
							SRLogger.writeLog("   Beschreibung wurde aktualisiert von %s auf %s" % (old_timerdescription, timer_description), True)
							timer.log(0, "[SerienRecorder] Changed description from %s to %s" % (old_timerdescription, timer_description))
						if updateDirectory:
							SRLogger.writeLog("   Verzeichnis wurde aktualisiert von %s auf %s" % (old_dirname, dirname), True)
							timer.log(0, "[SerienRecorder] Changed directory from %s to %s" % (old_dirname, dirname))
						self.countTimerUpdate += 1
						NavigationInstance.instance.RecordTimer.saveTimer()
						self.database.updateTimerStartTime(start_unixtime, eit, new_serien_title, serien_time, stbRef)
						timerUpdated = True
					else:
						print("[SerienRecorder] No timer update needed")
						# SRLogger.writeLog("' %s - %s '" % (title, dirname), True)
						# SRLogger.writeLog("   Timer muss nicht aktualisiert werden", True)
						timerUpdated = True
					break

		# Timer not found - maybe removed from image timer list
		if not timerFound:
			print("[SerienRecorder] Timer not found")
			SRLogger.writeLog("' %s - %s '" % (title, dirname), True)
			SRLogger.writeLog("   Timer konnte nicht aktualisiert werden, weil er nicht gefunden werden konnte!", True)

		return timerUpdated

	def search(self, NoOfRecords):
		if NoOfRecords:
			optionalText = " (%s. Wiederholung)" % NoOfRecords
		else:
			optionalText = ""

		SRLogger.writeLog("\n---------' Erstelle Timer%s '---------\n" % optionalText, True)

		transmissions = self.tempDB.getTransmissionsOrderedByNumberOfRecordings(NoOfRecords)
		for transmission in transmissions:
			(serien_name, serien_wlid, serien_fsid, markerType, staffel, episode, title, anzahl) = transmission
			(noOfRecords, preferredChannel, useAlternativeChannel) = self.database.getPreferredMarkerChannels(serien_wlid, config.plugins.serienRec.useAlternativeChannel.value, config.plugins.serienRec.NoOfRecords.value)

			(dirname, dirname_serie) = getDirname(self.database, serien_name, serien_fsid, staffel)
			self.enableDirectoryCreation = False

			self.konflikt = ""
			TimerDone = self.doSearch(serien_fsid, staffel, episode, title, optionalText, preferredChannel)
			if (not TimerDone) and useAlternativeChannel:
				if preferredChannel == 1:
					usedChannel = 2
				else:
					usedChannel = 1
				TimerDone = self.doSearch(serien_fsid, staffel, episode, title, optionalText, usedChannel)

			# Setze deaktivierten Timer
			if not TimerDone:
				if str(episode).isdigit():
					if int(episode) == 0:
						transmissionsForTimer = self.tempDB.getTransmissionsToCreateTimer(serien_fsid, staffel, episode, title)
					else:
						transmissionsForTimer = self.tempDB.getTransmissionsToCreateTimer(serien_fsid, staffel, episode)
				else:
					transmissionsForTimer = self.tempDB.getTransmissionsToCreateTimer(serien_fsid, staffel, episode)

				for transmissionForTimer in transmissionsForTimer:
					(current_time, future_time, serien_name, serien_wlid, serien_fsid, markerType, staffel, episode, check_SeasonEpisode, title, label_serie,
					 webChannel, stbChannel, stbRef, start_unixtime, end_unixtime, eit, altstbChannel, altstbRef,
					 alt_start_unixtime, alt_end_unixtime, alt_eit, dirname, AnzahlAufnahmen, fromTime, toTime,
					 vomMerkzettel, excludedWeekdays, updateFromEPG) = transmissionForTimer

					if preferredChannel == 1:
						timer_stbChannel = stbChannel
						timer_stbRef = stbRef
						timer_start_unixtime = start_unixtime
						timer_end_unixtime = end_unixtime
						timer_eit = eit
					else:
						timer_stbChannel = altstbChannel
						timer_stbRef = altstbRef
						timer_start_unixtime = alt_start_unixtime
						timer_end_unixtime = alt_end_unixtime
						timer_eit = alt_eit

					##############################
					#
					# Setze deaktivierten Timer
					#
					# Ueberpruefe ob der sendetermin zwischen der fromTime und toTime liegt
					start_time = (time.localtime(int(timer_start_unixtime)).tm_hour * 60) + time.localtime(int(timer_start_unixtime)).tm_min
					end_time = (time.localtime(int(timer_end_unixtime)).tm_hour * 60) + time.localtime(int(timer_end_unixtime)).tm_min
					if TimeHelpers.allowedTimeRange(fromTime, toTime, start_time, end_time):
						if self.doTimer(current_time, future_time, title, staffel, episode, label_serie,
						                timer_start_unixtime, timer_end_unixtime, timer_stbRef, timer_eit,
						                serien_name, serien_wlid, serien_fsid, markerType, webChannel, timer_stbChannel, optionalText,
						                vomMerkzettel, True):
							self.removeTransmission(episode, serien_fsid, staffel, start_unixtime, stbRef, title)
							break

				if len(self.konflikt) > 0:
					if config.plugins.serienRec.showMessageOnConflicts.value:
						self.messageList.append(("Timerkonflikte beim SerienRecorder Suchlauf:\n%s" % self.konflikt,
						                         MessageBox.TYPE_INFO, -1, self.konflikt))
						Notifications.AddPopup("Timerkonflikte beim SerienRecorder Suchlauf:\n%s" % self.konflikt,
						                       MessageBox.TYPE_INFO, timeout=-1, id=self.konflikt)

			##############################
			#
			# erstellt das serien verzeichnis
			if TimerDone and self.enableDirectoryCreation:
				STBHelpers.createDirectory(serien_fsid, markerType, dirname, dirname_serie)

	def doSearch(self, serien_fsid, staffel, episode, title, optionalText, usedChannel):
		# print "doSearch: %r" % serien_name
		# prepare postprocessing for forced recordings
		forceRecordings = []
		forceRecordings_W = []
		eventRecordings = []
		self.konflikt = ""

		TimerDone = False
		if str(episode).isdigit():
			if int(episode) == 0:
				transmissionsForTimer = self.tempDB.getTransmissionsToCreateTimer(serien_fsid, staffel, episode, title)
			else:
				transmissionsForTimer = self.tempDB.getTransmissionsToCreateTimer(serien_fsid, staffel, episode)
		else:
			transmissionsForTimer = self.tempDB.getTransmissionsToCreateTimer(serien_fsid, staffel, episode)

		self.tempDB.beginTransaction()
		for transmissionForTimer in transmissionsForTimer:
			(current_time, future_time, serien_name, serien_wlid, serien_fsid, markerType, staffel, episode, check_SeasonEpisode, title, label_serie,
			 webChannel, stbChannel, stbRef, start_unixtime, end_unixtime, eit, altstbChannel, altstbRef,
			 alt_start_unixtime, alt_end_unixtime, alt_eit, dirname, AnzahlAufnahmen, fromTime, toTime, vomMerkzettel,
			 excludedWeekdays, updateFromEPG) = transmissionForTimer

			# set the lead/follow-up time
			(margin_before, margin_after) = self.database.getMargins(serien_fsid, webChannel,
			                                                         config.plugins.serienRec.margin_before.value,
			                                                         config.plugins.serienRec.margin_after.value)

			start_unixtime = int(start_unixtime) - (int(margin_before) * 60)
			end_unixtime = int(end_unixtime) + (int(margin_after) * 60)

			if usedChannel == 1:
				timer_stbChannel = stbChannel
				timer_stbRef = stbRef
				timer_start_unixtime = start_unixtime
				timer_end_unixtime = end_unixtime
				timer_eit = eit
			else:
				timer_stbChannel = altstbChannel
				timer_stbRef = altstbRef
				timer_start_unixtime = alt_start_unixtime
				timer_end_unixtime = alt_end_unixtime
				timer_eit = alt_eit

			# Is channel assigned
			if timer_stbChannel == "":
				SRLogger.writeLogFilter("channels", "' %s ' - STB-Sender nicht in bevorzugter Senderliste zugewiesen -> ' %s '" % (label_serie, webChannel))
				# Nicht in bevorzugter Kanalliste - dann gehen wir davon aus, dass kein Timer angelegt werden soll.
				TimerDone = True
				continue

			##############################
			#
			# CHECK
			#
			# ueberprueft anhand des Seriennamen, Season, Episode ob die serie bereits auf der HDD existiert
			#
			# check ob timer existiert
			startTimeLowBound = int(timer_start_unixtime) - (int(STBHelpers.getEPGTimeSpan()) * 60)
			startTimeHighBound = int(timer_start_unixtime) + (int(STBHelpers.getEPGTimeSpan()) * 60)

			if self.database.timerExists(webChannel, serien_fsid, staffel, episode, startTimeLowBound, startTimeHighBound):
				SRLogger.writeLogFilter("added", "' %s ' - Timer für diese Episode%s wurde bereits erstellt -> ' %s '" % (label_serie, optionalText, check_SeasonEpisode))
				#self.removeTransmission(episode, serien_fsid, staffel, start_unixtime, stbRef, title)
				TimerDone = True
				continue

			# check anzahl timer und auf hdd
			bereits_vorhanden, bereits_vorhanden_HDD = self.countEpisode(check_SeasonEpisode, dirname, episode, serien_fsid, serien_name, staffel, title)

			if bereits_vorhanden >= AnzahlAufnahmen:
				SRLogger.writeLogFilter("added", "' %s ' - Eingestellte Anzahl Timer für diese Episode%s wurden bereits erstellt -> ' %s '" % (label_serie, optionalText, check_SeasonEpisode))
				TimerDone = True
				break

			if bereits_vorhanden_HDD >= AnzahlAufnahmen:
				SRLogger.writeLogFilter("disk", "' %s ' - Episode%s bereits auf HDD vorhanden -> ' %s '" % (label_serie, optionalText, check_SeasonEpisode))
				TimerDone = True
				break

			# check for excluded weekdays - this can be done early so we can skip all other checks
			# if the transmission date is on an excluded weekday
			if str(excludedWeekdays).isdigit():
				print("[SerienRecorder] - Excluded weekdays check")
				# SRLogger.writeLog("- Excluded weekdays check", True)
				transmissionDate = datetime.date.fromtimestamp((int(timer_start_unixtime)))
				weekday = transmissionDate.weekday()
				print("    Serie = %s, Datum = %s, Wochentag = %s" % (label_serie, time.strftime("%d.%m.%Y - %H:%M", time.localtime(int(timer_start_unixtime))),
					weekday))
				# SRLogger.writeLog("   Serie = %s, Datum = %s, Wochentag = %s" % (label_serie, time.strftime("%d.%m.%Y - %H:%M", time.localtime(int(timer_start_unixtime))), weekday), True)
				if excludedWeekdays & (1 << weekday) != 0:
					SRLogger.writeLogFilter("timeRange", "' %s ' - Wochentag auf der Ausnahmeliste -> ' %s '" % (label_serie, transmissionDate.strftime('%A')))
					TimerDone = True
					continue

			if config.plugins.serienRec.splitEventTimer.value != "0" and '/' in str(episode):
				# Event-Programmierung auflösen -> 01/1x02/1x03
				SRLogger.writeLogFilter("timerDebug", "Event-Programmierung gefunden: %s S%sE%s - %s" % (serien_name, str(staffel).zfill(2), str(episode).zfill(2), title))
				splitedSeasonEpisodeList, splitedTitleList, useTitles = self.splitEvent(episode, staffel, title)

				alreadyExistsCount = 0
				for idx, entry in enumerate(splitedSeasonEpisodeList):
					splitedTitle = "dump"
					if useTitles:
						splitedTitle = splitedTitleList[idx]
					alreadyExists = self.database.getNumberOfTimers(serien_fsid, entry[0], entry[1], splitedTitle, False)
					if alreadyExists:
						alreadyExistsCount += 1

				if len(splitedSeasonEpisodeList) == alreadyExistsCount:
					# Alle Einzelfolgen wurden bereits aufgenommen - der Event muss nicht mehr aufgenommen werden.
					SRLogger.writeLogFilter("timerDebug", "   ' %s ' - Timer für Einzelepisoden wurden bereits erstellt -> ' %s '" % (serien_name, check_SeasonEpisode))
					TimerDone = True
					continue
				elif config.plugins.serienRec.splitEventTimer.value == "2":
					# Nicht alle Einzelfolgen wurden bereits aufgenommen, es sollen aber Einzelfolgen bevorzugt werden
					SRLogger.writeLogFilter("timerDebug", "   ' %s ' - Versuche zunächst Timer für Einzelepisoden anzulegen" % serien_name)
					eventRecordings.append((title, staffel, episode, label_serie, timer_start_unixtime,
					                        timer_end_unixtime, timer_stbRef, timer_eit, dirname,
					                        serien_name, serien_wlid, serien_fsid, markerType, webChannel, timer_stbChannel, check_SeasonEpisode,
					                        vomMerkzettel, current_time, future_time))
					continue

			##############################
			#
			# CHECK
			#
			# Ueberpruefe ob der sendetermin zwischen der fromTime und toTime liegt und finde Wiederholungen auf dem gleichen Sender
			#
			# prepare valid time range
			if (int(fromTime) > 0) or (int(toTime) < (23 * 60) + 59):
				start_time = (time.localtime(int(timer_start_unixtime)).tm_hour * 60) + time.localtime(int(timer_start_unixtime)).tm_min
				end_time = (time.localtime(int(timer_end_unixtime)).tm_hour * 60) + time.localtime(int(timer_end_unixtime)).tm_min

				if not TimeHelpers.allowedTimeRange(fromTime, toTime, start_time, end_time):
					timeRangeConfigured = "%s:%s - %s:%s" % (str(int(fromTime) / 60).zfill(2), str(int(fromTime) % 60).zfill(2), str(int(toTime) / 60).zfill(2), str(int(toTime) % 60).zfill(2))
					timeRangeTransmission = "%s:%s - %s:%s" % (str(int(start_time) / 60).zfill(2), str(int(start_time) % 60).zfill(2), str(int(end_time) / 60).zfill(2), str(int(end_time) % 60).zfill(2))
					SRLogger.writeLogFilter("timeRange", "' %s ' - Sendung (%s) nicht in Zeitspanne [%s]" % (label_serie, timeRangeTransmission, timeRangeConfigured))

					# forced recording activated?
					if not config.plugins.serienRec.forceRecording.value:
						continue

					# backup timer data for post processing
					show_start = time.strftime("%d.%m.%Y - %H:%M", time.localtime(int(timer_start_unixtime)))
					SRLogger.writeLogFilter("timeRange", "' %s ' - Backup Timer -> %s" % (label_serie, show_start))
					forceRecordings.append((title, staffel, episode, label_serie, timer_start_unixtime,
					                        timer_end_unixtime, timer_stbRef, timer_eit, dirname, serien_name, serien_wlid, serien_fsid,
					                        markerType, webChannel, timer_stbChannel, check_SeasonEpisode, vomMerkzettel, current_time, future_time))
					continue

				##############################
				#
				# CHECK
				#
				# Ueberpruefe ob der sendetermin innerhalb der Wartezeit für Wiederholungen liegt
				#
				if config.plugins.serienRec.forceRecording.value:
					TimeSpan_time = int(future_time) + (int(config.plugins.serienRec.TimeSpanForRegularTimer.value) - int(config.plugins.serienRec.checkfordays.value)) * 86400
					if int(timer_start_unixtime) > int(TimeSpan_time):
						# backup timer data for post processing
						show_start = time.strftime("%d.%m.%Y - %H:%M", time.localtime(int(timer_start_unixtime)))
						SRLogger.writeLogFilter("timeRange", "' %s ' - Backup Timer -> %s" % (label_serie, show_start))
						forceRecordings_W.append((title, staffel, episode, label_serie, timer_start_unixtime,
						                          timer_end_unixtime, timer_stbRef, timer_eit, dirname, serien_name, serien_wlid, serien_fsid,
						                          markerType, webChannel, timer_stbChannel, check_SeasonEpisode, vomMerkzettel, current_time, future_time))
						continue

			##############################
			#
			# Setze Timer
			#
			if self.doTimer(current_time, future_time, title, staffel, episode, label_serie, timer_start_unixtime,
			                timer_end_unixtime, timer_stbRef, timer_eit, serien_name, serien_wlid, serien_fsid, markerType, webChannel,
			                timer_stbChannel, optionalText, vomMerkzettel):
				self.removeTransmission(episode, serien_fsid, staffel, timer_start_unixtime, timer_stbRef, title)
				TimerDone = True
				break

		### end of for loop
		self.tempDB.commitTransaction()

		if not TimerDone:
			# post processing for forced recordings
			for title, staffel, episode, label_serie, timer_start_unixtime, timer_end_unixtime, timer_stbRef, timer_eit, dirname, serien_name, serien_wlid, serien_fsid, markerType, webChannel, timer_stbChannel, check_SeasonEpisode, vomMerkzettel, current_time, future_time in forceRecordings_W:
				if self.database.getNumberOfTimers(serien_fsid, staffel, episode, title, False):
					continue
				# programmiere Timer (Wiederholung)
				if self.doTimer(current_time, future_time, title, staffel, episode, label_serie, timer_start_unixtime,
				                timer_end_unixtime, timer_stbRef, timer_eit, serien_name, serien_wlid, serien_fsid, markerType, webChannel,
				                timer_stbChannel, optionalText, vomMerkzettel):
					self.removeTransmission(episode, serien_fsid, staffel, timer_start_unixtime, timer_stbRef, title)
					TimerDone = True

		if not TimerDone:
			# post processing for forced recordings
			for title, staffel, episode, label_serie, timer_start_unixtime, timer_end_unixtime, timer_stbRef, timer_eit, dirname, serien_name, serien_wlid, serien_fsid, markerType, webChannel, timer_stbChannel, check_SeasonEpisode, vomMerkzettel, current_time, future_time in forceRecordings:
				if self.database.getNumberOfTimers(serien_fsid, staffel, episode, title, False):
					continue
				show_start = time.strftime("%d.%m.%Y - %H:%M", time.localtime(int(timer_start_unixtime)))
				SRLogger.writeLog("' %s ' - Keine Wiederholung gefunden! -> %s" % (label_serie, show_start), True)
				# programmiere Timer
				if self.doTimer(current_time, future_time, title, staffel, episode, label_serie, timer_start_unixtime,
				                timer_end_unixtime, timer_stbRef, timer_eit, serien_name, serien_wlid, serien_fsid, markerType, webChannel,
				                timer_stbChannel, optionalText, vomMerkzettel):
					self.removeTransmission(episode, serien_fsid, staffel, timer_start_unixtime, timer_stbRef, title)
					TimerDone = True

		if not TimerDone:
			# post processing event recordings
			for singleTitle, staffel, singleEpisode, label_serie, timer_start_unixtime, timer_end_unixtime, timer_stbRef, timer_eit, dirname, serien_name, serien_wlid, serien_fsid, markerType, webChannel, timer_stbChannel, check_SeasonEpisode, vomMerkzettel, current_time, future_time in eventRecordings[:]:
				if self.shouldCreateEventTimer(serien_fsid, staffel, singleEpisode, singleTitle):
					show_start = time.strftime("%d.%m.%Y - %H:%M", time.localtime(int(timer_start_unixtime)))
					SRLogger.writeLog("   ' %s ' - Einzelepisoden nicht gefunden! -> %s" % (label_serie, show_start),
					                  True)
					# programmiere Timer
					if self.doTimer(current_time, future_time, title, staffel, episode, label_serie, timer_start_unixtime,
					                timer_end_unixtime, timer_stbRef, timer_eit, serien_name, serien_wlid, serien_fsid, markerType, webChannel,
					                timer_stbChannel, optionalText, vomMerkzettel):
						TimerDone = True

		return TimerDone

	def countEpisode(self, check_SeasonEpisode, dirname, episode, serien_fsid, serien_name, staffel, title):
		bereits_vorhanden_HDD = 0
		if str(episode).isdigit():
			if int(episode) == 0:
				bereits_vorhanden = self.database.getNumberOfTimers(serien_fsid, staffel, episode, title, searchOnlyActiveTimers=True)
				if config.plugins.serienRec.sucheAufnahme.value:
					bereits_vorhanden_HDD = STBHelpers.countEpisodeOnHDD(dirname, check_SeasonEpisode, serien_name, False, title)
			else:
				bereits_vorhanden = self.database.getNumberOfTimers(serien_fsid, staffel, episode, searchOnlyActiveTimers=True)
				if config.plugins.serienRec.sucheAufnahme.value:
					bereits_vorhanden_HDD = STBHelpers.countEpisodeOnHDD(dirname, check_SeasonEpisode, serien_name, False)
		else:
			bereits_vorhanden = self.database.getNumberOfTimers(serien_fsid, staffel, episode, searchOnlyActiveTimers=True)
			if config.plugins.serienRec.sucheAufnahme.value:
				bereits_vorhanden_HDD = STBHelpers.countEpisodeOnHDD(dirname, check_SeasonEpisode, serien_name, False)
		return bereits_vorhanden, bereits_vorhanden_HDD

	def removeTransmission(self, episode, serien_fsid, staffel, timer_start_unixtime, timer_stbRef, title):
		if str(episode).isdigit():
			if int(episode) == 0:
				self.tempDB.removeTransmission(serien_fsid, staffel, episode, title, timer_start_unixtime, timer_stbRef)
			else:
				self.tempDB.removeTransmission(serien_fsid, staffel, episode, None, timer_start_unixtime, timer_stbRef)
		else:
			self.tempDB.removeTransmission(serien_fsid, staffel, episode, None, timer_start_unixtime, timer_stbRef)

	def doTimer(self, current_time, future_time, title, staffel, episode, label_serie, start_unixtime, end_unixtime,
	            stbRef, eit, serien_name, serien_wlid, serien_fsid, markerType, webChannel, stbChannel, optionalText='',
	            vomMerkzettel=False, tryDisabled=False):

		seasonEpisodeString = "S%sE%s" % (str(staffel).zfill(2), str(episode).zfill(2))

		(margin_before, margin_after) = self.database.getMargins(serien_fsid, webChannel,
		                                                         config.plugins.serienRec.margin_before.value,
		                                                         config.plugins.serienRec.margin_after.value)

		epgSeriesName = self.database.getMarkerEPGName(serien_fsid)

		# try to get eventID (eit) from epgCache
		if config.plugins.serienRec.eventid.value and self.database.getUpdateFromEPG(serien_fsid):
			print("[SerienRecorder] Update data from EPG")
			eit, start_unixtime, end_unixtime = STBHelpers.getStartEndTimeFromEPG(start_unixtime, end_unixtime, margin_before, margin_after, serien_name, stbRef)
			if eit is 0 and len(epgSeriesName) > 0 and epgSeriesName != serien_name:
				eit, start_unixtime, end_unixtime = STBHelpers.getStartEndTimeFromEPG(start_unixtime, end_unixtime, margin_before, margin_after, epgSeriesName, stbRef)

		start_unixtime = int(start_unixtime) - (int(margin_before) * 60)
		end_unixtime = int(end_unixtime) + (int(margin_after) * 60)

		show_start = time.strftime("%d.%m.%Y - %H:%M", time.localtime(int(start_unixtime)))
		show_end = time.strftime("%d.%m.%Y - %H:%M", time.localtime(int(end_unixtime)))

		if int(start_unixtime) > int(future_time):
			show_future = time.strftime("%d.%m.%Y - %H:%M", time.localtime(int(future_time)))
			SRLogger.writeLogFilter("timeLimit", "' %s ' - Timer wird evtl. später angelegt -> Sendetermin: %s - Erlaubte Zeitspanne bis %s" % (label_serie, show_start, show_future))
			return True
		if int(current_time) > int(start_unixtime):
			show_current = time.strftime("%d.%m.%Y - %H:%M", time.localtime(int(current_time)))
			SRLogger.writeLogFilter("timeLimit", "' %s ' - Der Sendetermin liegt in der Vergangenheit: %s - Aktuelles Datum: %s" % (label_serie, show_start, show_current))
			return True

		# get VPS settings for channel
		vpsSettings = self.database.getVPS(serien_fsid, webChannel)

		# get tags from marker
		tags = self.database.getTags(serien_wlid)

		# get addToDatabase for marker
		addToDatabase = self.database.getAddToDatabase(serien_wlid)

		# get autoAdjust for marker
		autoAdjust = self.database.getAutoAdjust(serien_wlid, webChannel)

		# install missing covers
		(dirname, dirname_serie) = getDirname(self.database, serien_name, serien_fsid, staffel)
		STBHelpers.createDirectory(serien_fsid, markerType, dirname, dirname_serie, True)

		# versuche timer anzulegen
		# setze strings für addtimer
		if STBHelpers.checkTuner(start_unixtime, end_unixtime, stbRef):
			timer_name = self.getTimerName(serien_name, staffel, episode, title, markerType)
			result = serienRecBoxTimer.addTimer(stbRef, str(start_unixtime), str(end_unixtime), timer_name,
			                                    "%s - %s" % (seasonEpisodeString, title),
			                                    eit, False, dirname, vpsSettings, tags, autoAdjust, None)
			# SRLogger.writeLog("%s: %s => %s" % (timer_name, str(start_unixtime), str(end_unixtime)), True)
			if result["result"]:
				self.countTimer += 1
				# Eintrag in die Datenbank
				self.addTimerToDB(serien_name, serien_wlid, serien_fsid, staffel, episode, title, start_unixtime, stbRef, webChannel, eit, addToDatabase)
				if vomMerkzettel:
					self.countTimerFromWishlist += 1
					SRLogger.writeLog("' %s ' - Timer (vom Merkzettel) wurde angelegt%s -> [%s] - [%s] %s @ %s" % (label_serie, optionalText, show_start, show_end, timer_name, stbChannel), True)
					self.database.updateBookmark(serien_fsid, staffel, episode)
					self.database.removeBookmark(serien_fsid, staffel, episode)
				else:
					SRLogger.writeLog("' %s ' - Timer wurde angelegt%s -> [%s] - [%s] %s @ %s" % (label_serie, optionalText, show_start, show_end, timer_name, stbChannel), True)
					# Event-Programmierung verarbeiten
					if (config.plugins.serienRec.splitEventTimer.value == "1" or (config.plugins.serienRec.splitEventTimer.value == "2" and config.plugins.serienRec.addSingleTimersForEvent.value == "1")) and '/' in str(episode):
						splitedSeasonEpisodeList, splitedTitleList, useTitles = self.splitEvent(episode, staffel, title)
						for idx, entry in enumerate(splitedSeasonEpisodeList):
							splitedTitle = "dump"
							if useTitles:
								splitedTitle = splitedTitleList[idx]
							alreadyExists = self.database.getNumberOfTimers(serien_fsid, entry[0], entry[1], splitedTitle, False)
							if alreadyExists == 0 and addToDatabase:
								# Nicht vorhandene Einzelfolgen als bereits aufgenommen markieren
								self.database.addToTimerList(serien_name, serien_fsid, entry[1], entry[1], entry[0], splitedTitle, int(time.time() - 10), "", "", 0, 1)
								SRLogger.writeLogFilter("timerDebug", "   Für die Einzelepisode wird kein Timer mehr erstellt: %s S%sE%s - %s" % (serien_name, str(entry[0]).zfill(2), str(entry[1]).zfill(2), splitedTitle))

				self.enableDirectoryCreation = True
				return True
			elif not tryDisabled:
				self.konflikt = result["message"].replace("! ", "!\n").replace(" / ", "\n")
				print("' %s ' - ACHTUNG! -> %s" % (label_serie, result["message"]))
				SRLogger.writeLog("' %s ' - Timer konnte nicht angelegt werden%s -> [%s] - [%s] %s @ %s" % (
				label_serie, optionalText, show_start, show_end, timer_name, stbChannel), True)
				SRLogger.writeLog("' %s ' - ACHTUNG! -> %s" % (label_serie, result["message"]), True)
			else:
				self.konflikt = result["message"].replace("! ", "!\n").replace(" / ", "\n")
				print("' %s ' - ACHTUNG! -> %s" % (label_serie, result["message"]))
				SRLogger.writeLog("' %s ' - ACHTUNG! -> %s" % (label_serie, result["message"]), True)
				dbMessage = result["message"].replace("In Konflikt stehende Timer vorhanden!", "").strip()

				result = serienRecBoxTimer.addTimer(stbRef, str(start_unixtime), str(end_unixtime), timer_name,
				                                    "%s - %s" % (seasonEpisodeString, title), eit, True,
				                                    dirname, vpsSettings, tags, autoAdjust, None)
				if result["result"]:
					self.countNotActiveTimer += 1
					# Eintrag in die Datenbank
					self.addTimerToDB(serien_name, serien_wlid, serien_fsid, staffel, episode, title, start_unixtime, stbRef, webChannel, eit, addToDatabase, False)
					self.database.addTimerConflict(dbMessage, start_unixtime, webChannel)
					if vomMerkzettel:
						self.countTimerFromWishlist += 1
						SRLogger.writeLog(
							"' %s ' - Timer (vom Merkzettel) wurde deaktiviert angelegt%s -> [%s] - [%s] %s @ %s" % (
							label_serie, optionalText, show_start, show_end, timer_name, stbChannel), True)
					else:
						SRLogger.writeLog("' %s ' - Timer wurde deaktiviert angelegt%s -> [%s] - [%s] %s @ %s" % (
						label_serie, optionalText, show_start, show_end, timer_name, stbChannel), True)
					self.enableDirectoryCreation = True
					return True
				else:
					self.konflikt = result["message"].replace("! ", "!\n").replace(" / ", "\n")
					print("' %s ' - ACHTUNG! -> %s" % (label_serie, result["message"]))
					SRLogger.writeLog("' %s ' - ACHTUNG! -> %s" % (label_serie, result["message"]), True)
		else:
			print("Tuner belegt %s %s" % (label_serie, show_start))
			SRLogger.writeLog("Tuner belegt: %s %s" % (label_serie, show_start), True)
		return False

	def addTimerToDB(self, serien_name, serien_wlid, serien_fsid, staffel, episode, title, start_time, stbRef, webChannel, eit, addToDatabase, TimerAktiviert=True):
		seasonEpisodeString = "S%sE%s" % (str(staffel).zfill(2), str(episode).zfill(2))
		if not addToDatabase:
			print("[SerienRecorder] Timer angelegt: %s %s - %s" % (serien_name, seasonEpisodeString, title))
			SRLogger.writeLogFilter("timerDebug", "   Timer angelegt: %s %s - %s" % (serien_name, seasonEpisodeString, title))
		else:
			#(margin_before, margin_after) = self.database.getMargins(serien_fsid, webChannel,
			#                                                         config.plugins.serienRec.margin_before.value,
			#                                                         config.plugins.serienRec.margin_after.value)

			timerStartTime = int(start_time) #- (int(margin_before) * 60)

			if self.database.timerExistsByServiceRef(serien_fsid, stbRef, timerStartTime, timerStartTime):

				self.database.updateTimerEIT(serien_fsid, stbRef, eit, timerStartTime, timerStartTime, TimerAktiviert)
				print("[SerienRecorder] Timer bereits vorhanden: %s %s - %s" % (serien_name, seasonEpisodeString, title))
				SRLogger.writeLog("   Timer bereits vorhanden: %s %s - %s" % (serien_name, seasonEpisodeString, title))
			else:
				self.database.addToTimerList(serien_name, serien_fsid, episode, episode, staffel, title, start_time, stbRef, webChannel, eit, TimerAktiviert)
				print("[SerienRecorder] Timer angelegt: %s %s - %s" % (serien_name, seasonEpisodeString, title))
				SRLogger.writeLogFilter("timerDebug", "   Timer angelegt: %s %s - %s" % (serien_name, seasonEpisodeString, title))


	def shouldCreateEventTimer(self, serien_fsid, staffel, episode, title):
		if self.database.getNumberOfTimers(serien_fsid, staffel, episode, title, False):
			return False

		result = True
		if config.plugins.serienRec.splitEventTimer.value != "2" and '/' in str(episode):
			# Event-Programmierung auflösen -> 01/1x02/1x03
			splitedSeasonEpisodeList = []
			if 'x' in str(episode):
				episode = str(staffel) + 'x' + str(episode)
				seasonEpisodeList = episode.split('/')
				for seasonEpisode in seasonEpisodeList:
					splitedSeasonEpisodeList.append(seasonEpisode.split('x'))
			else:
				seasonEpisodeList = episode.split('/')
				for seasonEpisode in seasonEpisodeList:
					seasonEpisode = str(staffel) + 'x' + str(seasonEpisode)
					splitedSeasonEpisodeList.append(seasonEpisode.split('x'))

			useTitles = True
			splitedTitleList = title.split('/')
			if len(splitedTitleList) != len(splitedSeasonEpisodeList):
				useTitles = False

			# Möglichst die Einzelfolgen bevorzugen und Event ignorieren
			alreadyExistsCount = 0
			for idx,entry in enumerate(splitedSeasonEpisodeList):
				title = "dump"
				if useTitles:
					title = splitedTitleList[idx]
				alreadyExists = self.database.getNumberOfTimers(serien_fsid, entry[0], entry[1], title, False)
				if alreadyExists:
					alreadyExistsCount += 1

			if alreadyExistsCount == len(splitedSeasonEpisodeList):
				result = False

		return result

	def adjustEPGtimes(self, current_time):
		SRLogger.writeLog("\n---------' Aktualisiere Timer '---------\n", True)

		##############################
		#
		# try to get eventID (eit) from epgCache
		#

		recordHandler = NavigationInstance.instance.RecordTimer
		#SRLogger.writeLog("<< Suche im EPG anhand der Uhrzeit", True)
		timers = self.database.getAllTimer(current_time)
		for timer in timers:
			(serien_name, staffel, episode, serien_title, serien_time, stbRef, webChannel, eit, active, serien_fsid) = timer

			channelName = STBHelpers.getChannelByRef(self.channelList, stbRef)
			title = "%s - S%sE%s - %s" % (serien_name, str(staffel).zfill(2), str(episode).zfill(2), serien_title)
			print("[SerienRecorder] Update request for timer: %s [%d]" % (title, serien_time))

			markerType = self.database.getMarkerType(serien_fsid)
			if markerType is None:
				# Marker type not found in database => it's a movie
				markerType = 1
			else:
				markerType = int(markerType)

			epgSeriesName = self.database.getMarkerEPGName(serien_fsid)
			(margin_before, margin_after) = self.database.getMargins(serien_fsid, webChannel, config.plugins.serienRec.margin_before.value, config.plugins.serienRec.margin_after.value)
			db_serien_time = int(serien_time)+(int(margin_before) * 60)
			transmission = self.tempDB.getTransmissionForTimerUpdate(serien_fsid, staffel, episode, db_serien_time)
			if transmission:
				(new_serien_name, serien_wlid, serien_fsid, new_staffel, new_episode, new_serien_title, new_serien_time, updateFromEPG) = transmission
				print("[SerienRecorder] Get transmission from database: %s [%d]" % (new_serien_title, new_serien_time))
			else:
				print("[SerienRecorder] No transmission found for timer - update from EPG only")
				new_serien_name = serien_name
				new_staffel = staffel
				new_episode = episode
				new_serien_title = serien_title
				new_serien_time = 0
				updateFromEPG = self.database.getUpdateFromEPG(serien_fsid)

			title = "%s - S%sE%s - %s" % (new_serien_name, str(new_staffel).zfill(2), str(new_episode).zfill(2), new_serien_title)

			# event_matches = STBHelpers.getEPGEvent(['RITBDSE',("1:0:19:EF75:3F9:1:C00000:0:0:0:", 0, 1392755700, -1)], "1:0:19:EF75:3F9:1:C00000:0:0:0:", "2 Broke Girls", 1392755700)
			(no_events_found, event_matches) = STBHelpers.getEPGEvent(stbRef, serien_name, int(serien_time)+(int(margin_before) * 60))
			new_event_matches = None
			no_new_events_found = True
			if serien_time != new_serien_time and new_serien_time != 0:
				(no_new_events_found, new_event_matches) = STBHelpers.getEPGEvent(stbRef, new_serien_name, int(new_serien_time)+(int(margin_before) * 60))

			(dirname, dirname_serie) = getDirname(self.database, new_serien_name, serien_fsid, new_staffel)
			if no_events_found and no_new_events_found:
				SRLogger.writeLog("' %s - %s '" % (title, dirname), True)
				SRLogger.writeLog("   Timer konnte nicht aus dem EPG aktualisiert werden, nicht genügend EPG Daten vorhanden @ %s" % channelName)
			else:
				if new_event_matches and len(new_event_matches) > 0 and (not event_matches or (event_matches and len(event_matches) == 0)):
					# Old event not found but new one with different start time
					event_matches = new_event_matches
				elif len(epgSeriesName) > 0 and epgSeriesName != new_serien_name:
					# Try to find event with alternative epg series name
					(no_events_found, event_matches) = STBHelpers.getEPGEvent(stbRef, epgSeriesName, int(serien_time) + (int(margin_before) * 60))

				if event_matches and len(event_matches) > 0:
					for event_entry in event_matches:
						eit = int(event_entry[1])

						if config.plugins.serienRec.eventid.value and updateFromEPG:
							start_unixtime = int(event_entry[3]) - (int(margin_before) * 60)
							end_unixtime = int(event_entry[3]) + int(event_entry[4]) + (int(margin_after) * 60)
						else:
							start_unixtime = None
							end_unixtime = None

						print("[SerienRecorder] try to modify enigma2 timer: %s [%d]" % (title, serien_time))

						if (str(new_staffel) is 'S' or str(new_staffel) is '0') and (str(new_episode) is '0' or str(new_episode) is '00'):
							SRLogger.writeLog("' %s - %s '" % (title, dirname), True)
							SRLogger.writeLog("   Timer kann nicht aktualisiert werden @ %s" % channelName, True)
							break

						# get VPS settings for channel
						vpsSettings = self.database.getVPS(serien_fsid, webChannel)

						try:
							# suche in aktivierten Timern
							self.update(recordHandler.timer_list + recordHandler.processed_timers, eit, end_unixtime, new_episode,
															new_serien_title, serien_name, serien_fsid, serien_time,
															new_staffel, start_unixtime, stbRef, title,
															dirname, vpsSettings, markerType)

						except Exception:
							print("[SerienRecorder] Modifying enigma2 timer failed:", title, serien_time)
							SRLogger.writeLog("' %s - %s '" % (title, dirname), True)
							SRLogger.writeLog("   Timeraktualisierung fehlgeschlagen @ %s" % channelName, True)
						break
				else:
					SRLogger.writeLog("' %s - %s '" % (title, dirname), True)
					SRLogger.writeLog("   Timer konnte nicht aus dem EPG aktualisiert werden, die Sendung wurde im Zeitfenster nicht gefunden @ %s" % channelName)


	@staticmethod
	def splitEvent(episode, staffel, title):
		splitedSeasonEpisodeList = []
		if 'x' in str(episode):
			seasonEpisodeList = episode.split('/')
			for seasonEpisode in seasonEpisodeList:
				if not 'x' in seasonEpisode:
					seasonEpisode = str(staffel) + 'x' + str(seasonEpisode)
				splitedSeasonEpisodeList.append(seasonEpisode.split('x'))
		else:
			seasonEpisodeList = episode.split('/')
			for seasonEpisode in seasonEpisodeList:
				seasonEpisode = str(staffel) + 'x' + str(seasonEpisode)
				splitedSeasonEpisodeList.append(seasonEpisode.split('x'))
		useTitles = True
		splitedTitleList = title.split('/')
		if len(splitedTitleList) != len(splitedSeasonEpisodeList):
			useTitles = False
		return splitedSeasonEpisodeList, splitedTitleList, useTitles


# ---------------------------------- Timer Functions ------------------------------------------

class serienRecBoxTimer:

	def __init__(self):
		pass

	@staticmethod
	def getTimersTime():

		recordHandler = NavigationInstance.instance.RecordTimer
		timers = []

		for timer in recordHandler.timer_list:
			timers.append((timer.name, timer.begin, timer.end, timer.service_ref))
		return timers

	@staticmethod
	def getTimersList():

		recordHandler = NavigationInstance.instance.RecordTimer

		timers = []
		serienRec_chlist = STBHelpers.buildSTBChannelList()

		for timer in recordHandler.timer_list:
			if timer and timer.service_ref and timer.eit is not None:

				location = 'NULL'
				recordedfile = 'NULL'
				if timer.dirname:
					location = timer.dirname
				channel = STBHelpers.getChannelByRef(serienRec_chlist, str(timer.service_ref))
				if channel:
					# recordedfile = getRecordFilename(timer.name,timer.description,timer.begin,channel)
					recordedfile = str(timer.begin) + " - " + str(timer.service_ref) + " - " + str(timer.name)
				timers.append({
					"title": timer.name,
					"description": timer.description,
					"id_channel": 'NULL',
					"channel": channel,
					"id_genre": 'NULL',
					"begin": timer.begin,
					"end": timer.end,
					"serviceref": timer.service_ref,
					"location": location,
					"recordedfile": recordedfile,
					"tags": timer.tags,
					"eit": timer.eit
				})
		return timers

	@staticmethod
	def removeTimerEntry(serien_name, start_time, eit=0):

		recordHandler = NavigationInstance.instance.RecordTimer
		removed = False
		print("[SerienRecorder] try to remove enigma2 Timer:", serien_name, start_time)

		# entferne aktivierte Timer
		for timer in recordHandler.timer_list:
			if timer and timer.service_ref:
				if eit > 0:
					if timer.eit == eit:
						recordHandler.removeEntry(timer)
						removed = True
						break
				if str(timer.name) == serien_name and int(timer.begin) == int(start_time):
					# if str(timer.service_ref) == entry_dict['channelref']:
					recordHandler.removeEntry(timer)
					removed = True

		# entferne deaktivierte Timer
		if not removed:
			for timer in recordHandler.processed_timers:
				if timer and timer.service_ref:
					if eit > 0:
						if timer.eit == eit:
							recordHandler.removeEntry(timer)
							removed = True
							break
					if str(timer.name) == serien_name and int(timer.begin) == int(start_time):
						# if str(timer.service_ref) == entry_dict['channelref']:
						recordHandler.removeEntry(timer)
						removed = True

		return removed

	@staticmethod
	def addTimer(serviceref, begin, end, name, description, eit, disabled, dirname, vpsSettings, tags, autoAdjust, logentries=None):
		from SerienRecorderHelpers import isVTI
		recordHandler = NavigationInstance.instance.RecordTimer
		try:
			try:
				timer = RecordTimerEntry(
					ServiceReference(serviceref),
					begin,
					end,
					name,
					description,
					eit,
					disabled=disabled,
					justplay=config.plugins.serienRec.justplay.value,
					zapbeforerecord=config.plugins.serienRec.zapbeforerecord.value,
					justremind=config.plugins.serienRec.justremind.value,
					afterEvent=int(config.plugins.serienRec.afterEvent.value),
					dirname=dirname)
			except Exception:
				sys.exc_clear()

				timer = RecordTimerEntry(
					ServiceReference(serviceref),
					begin,
					end,
					name,
					description,
					eit,
					disabled,
					config.plugins.serienRec.justplay.value | config.plugins.serienRec.justremind.value,
					afterEvent=int(config.plugins.serienRec.afterEvent.value),
					dirname=dirname,
					tags=None)

			timer.repeated = 0
			try:
				if isVTI() and autoAdjust is not None:
					print("[SerienRecorder] Current autoAdjust for timer [%s]: %s" % (name, str(timer.autoadjust)))
					print("[SerienRecorder] autoAdjust is: %s" % str(autoAdjust))
					timer.autoadjust = autoAdjust
					print("[SerienRecorder] Set autoAdjust for timer [%s] to: %s" % (name, str(timer.autoadjust)))
			except:
				print("[SerienRecorder] Failed to set autoAdjust for timer [%s] - missconfigured database" % name)

			# Add tags
			timerTags = timer.tags[:]
			timerTags.append('SerienRecorder')
			if len(tags) != 0:
				timerTags.extend(tags)
			timer.tags = timerTags

			# If eit = 0 the VPS plugin won't work properly for this timer, so we have to disable VPS in this case.
			if SerienRecorder.VPSPluginAvailable and eit is not 0:
				timer.vpsplugin_enabled = vpsSettings[0]
				timer.vpsplugin_overwrite = timer.vpsplugin_enabled and (not vpsSettings[1])

			if logentries:
				timer.log_entries = logentries

			timer.log(0, "[SerienRecorder] Timer angelegt")

			conflicts = recordHandler.record(timer)
			if conflicts:
				errors = []
				for conflict in conflicts:
					errors.append(conflict.name)

				return {
					"result": False,
					"message": "In Konflikt stehende Timer vorhanden! %s" % " / ".join(errors)
				}
		except Exception, e:
			print("[%s] <%s>" % (__name__, e))
			return {
				"result": False,
				"message": "Timer konnte nicht angelegt werden '%s'!" % e
			}

		print("[SerienRecorder] Versuche Timer anzulegen:", name, dirname)
		SRLogger.writeLogFilter("timerDebug", "Versuche Timer anzulegen: ' %s - %s '" % (name, dirname))
		return {
			"result": True,
			"message": "Timer '%s' angelegt" % name,
			"eit": eit
		}

