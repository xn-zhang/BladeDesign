// Request coordinator shared by batch controls and historical/generated previews.
export class BatchRequests {
  constructor(session,revision){this.session=session;this.revision=revision;this.serial=0;}
  invalidate(){this.serial++;}
  previewTicket(){const session=this.session(),revision=this.revision(),serial=++this.serial;return ()=>this.session()===session&&this.revision()===revision&&this.serial===serial;}
  async control({id,selected,request,apply,refresh,busy}){
    const session=this.session(),current=()=>this.session()===session&&selected()===id;
    busy(true);
    try{const result=await request(id);if(!current())return;apply(result);await refresh(id);}
    finally{if(this.session()===session)busy(false);}
  }
}
