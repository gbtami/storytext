
""" Eclipse RCP has its own mechanism for background processing
    Hook application events directly into that for synchronisation."""

import logging, os
import storytext.guishared
from storytext.javaswttoolkit.simulator import DisplayFilter
from org.eclipse.core.runtime.jobs import Job, JobChangeAdapter
from threading import Lock, currentThread

class JobListener(JobChangeAdapter):
    # Add things from customwidgetevents here, if desired...
    systemJobNames = os.getenv("STORYTEXT_SYSTEM_JOB_NAMES", "").split(",")
    timeDelays = {}
    instance = None
    appEventPrefix = "completion of "
    def __init__(self):
        self.jobNamesToUse = {}
        self.jobCount = 0
        self.customUsageMethod = None
        self.jobCountLock = Lock()
        self.logger = logging.getLogger("Eclipse RCP jobs")
        
    def done(self, e):
        storytext.guishared.catchAll(self.jobDone, e)
        
    def jobDone(self, e):
        jobName = e.getJob().getName().lower()
        self.jobCountLock.acquire()
        if self.jobCount > 0:
            self.jobCount -= 1
        self.logger.debug("Completed " + ("system" if e.getJob().isSystem() else "non-system") + " job '" + jobName + "' jobs = " + repr(self.jobCount))    
        # We wait for the system to reach a stable state, i.e. no scheduled jobs
        # Would be nice to call Job.getJobManager().isIdle(),
        # but that doesn't count scheduled jobs for some reason
        noScheduledJobs = self.jobCount == 0
        if noScheduledJobs and self.jobNamesToUse:
            self.setComplete()
        self.jobCountLock.release()        
        
    def setComplete(self):
        for currCat, currJobName in self.jobNamesToUse.items():
            timeDelay = self.timeDelays.get(currJobName, 0.001)
            DisplayFilter.registerApplicationEvent(self.appEventPrefix + currJobName, category=currCat, timeDelay=timeDelay)
        self.jobNamesToUse = {}

    def scheduled(self, e):
        storytext.guishared.catchAll(self.jobScheduled, e)
        
    def jobScheduled(self, e):
        self.jobCountLock.acquire()
        parentJob = Job.getJobManager().currentJob()
        self.registerScheduled(e.getJob(), parentJob, currentThread().getName())
        self.jobCountLock.release()

    def registerScheduled(self, job, parentJob, threadName):
        jobName = job.getName().lower()
        self.jobCount += 1
        parentJobName = parentJob.getName().lower() if parentJob else ""
        category = "jobs_" + threadName
        postfix = ", parent job " + parentJobName if parentJobName else "" 
        self.logger.debug("Scheduled job '" + jobName + "' jobs = " + repr(self.jobCount) + ", thread = " + threadName + postfix)
        if jobName in self.systemJobNames or self.shouldUseJob(job):
            self.logger.debug("Now using job name '" + jobName + "' for category '" + category + "'")
            self.jobNamesToUse[category] = jobName
            self.removeJobName(parentJobName)
            def matchName(eventName, delayLevel):
                return eventName == self.appEventPrefix + parentJobName
            DisplayFilter.removeApplicationEvent(matchName)

#        from storytext.javaswttoolkit.util import getPrivateField
#        listeners = list(getPrivateField(getPrivateField(Job.getJobManager(), "jobListeners"), "global").getListeners())
#        print "Listeners now", listeners


    def shouldUseJob(self, job):
        return not job.isSystem() or (self.customUsageMethod and self.customUsageMethod(job))
            
    def removeJobName(self, jobName):
        for currCat, currJobName in self.jobNamesToUse.items():
            if currJobName == jobName:
                self.logger.debug("Removing job name '" + jobName + "' for category '" + currCat + "'")
                del self.jobNamesToUse[currCat]
                return        

    def enableListener(self):
        self.jobCountLock.acquire()
        self.logger.debug("Enabling Job Change Listener in thread " + currentThread().getName())
        Job.getJobManager().addJobChangeListener(self)
        startupJob = Job.getJobManager().currentJob()
        self.registerScheduled(startupJob, parentJob=None, threadName="MainThread")
        for job in Job.getJobManager().find(None):
            if job is not startupJob:
                self.registerScheduled(job, startupJob, threadName=job.getName())
        self.jobCountLock.release()    
            
    @classmethod
    def enable(cls, *args):
        JobListener.instance = cls(*args)
        cls.instance.enableListener()
