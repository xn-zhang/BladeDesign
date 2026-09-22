export class IdentityEpoch {
  constructor(){this.userId=null;this.generation=0;}
  update(id){if(this.userId===(id||null))return false;this.userId=id||null;this.generation++;return true;}
  capture(){return this.generation;}
  check(value){if(value!==this.generation)throw new DOMException('账号已变化，请重新操作','AbortError');}
}
