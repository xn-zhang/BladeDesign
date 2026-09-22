"""Per-user services. No request may change the identity of another instance."""
import pathlib,tempfile,threading
from design_assistant import ModelService
from model_transport import PublicModelTransport
from session_store import AuthError
class Slots:
    def __init__(self,shared):self.local=threading.BoundedSemaphore(2);self.shared=shared
    def acquire(self,blocking=False):
        if not self.local.acquire(blocking=False):return False
        if self.shared.acquire(blocking=False):return True
        self.local.release();return False
    def release(self):self.shared.release();self.local.release()
class UserServices:
    def __init__(self,state,models,manager=None,evaluation=None,batches=None):
        self.state=state;self.admin_models=models;self.manager=manager;self.evaluation=evaluation;self.batches=batches
        self.lock=threading.RLock();self.entries={};self.model_slots=threading.BoundedSemaphore(8);self.task_slots=threading.BoundedSemaphore(4)
        self.temporary=tempfile.TemporaryDirectory() if state.path is None else None
        self.root=(state.path.parent if state.path else pathlib.Path(self.temporary.name))/'users'
        models.slots=Slots(self.model_slots)
        if evaluation:evaluation.shared_slots=self.task_slots
        self.closed=False
    def for_user(self,principal,compute=False):
        uid=principal['user_id'];user=self.state.require_user(uid)
        if user['role']=='admin':return {'models':self.admin_models,'evaluation':self.evaluation,'batches':self.batches}
        with self.lock:
            if uid not in self.entries:
                self.entries[uid]={'models':ModelService(environ={},store=self.state.model_store(uid),transport=PublicModelTransport(),slots=Slots(self.model_slots)),'evaluation':None,'batches':None}
            entry=self.entries[uid]
            if compute and entry['evaluation'] is None:
                from evaluation_service import EvaluationService
                from batch_service import BatchService
                root=self.root/uid
                if self.root.is_symlink() or root.is_symlink() or root.resolve()!=self.root.resolve()/uid:raise ValueError('用户目录无效')
                root.mkdir(parents=True,exist_ok=True,mode=0o700)
                for child in ('evaluation','jobs'):
                    if (root/child).is_symlink():raise ValueError('用户目录无效')
                ev=EvaluationService(root/'evaluation',root/'jobs',None,max_active=2,shared_slots=self.task_slots)
                batches=BatchService(root/'evaluation',None,start_pump=False);ev.batch_service=batches
                entry.update(evaluation=ev,batches=batches)
            return entry
    def disable(self,uid):
        with self.lock:
            entry=self.entries.pop(uid,None)
            if entry:
                if entry['batches']:entry['batches'].shutdown()
                if entry['evaluation']:entry['evaluation'].shutdown()
    def close(self):
        with self.lock:
            if self.closed:return
            self.closed=True
            for uid in list(self.entries):self.disable(uid)
            if self.temporary:self.temporary.cleanup()
