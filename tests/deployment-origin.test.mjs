import test from 'node:test';
import assert from 'node:assert/strict';
import {canConnectService} from '../aeroblade/web/deployment-origin.js';
test('HTTP LAN workbench connects to private IP services',()=>{
  for(const host of ['192.168.1.2','10.1.2.3','172.16.1.2','172.31.255.254','localhost','127.0.0.1'])
    assert.equal(canConnectService(new URL(`http://${host}:8787`),'http:'),true);
});
test('public HTTP and mixed content remain rejected',()=>{
  for(const host of ['8.8.8.8','172.32.1.1','app.example'])
    assert.equal(canConnectService(new URL(`http://${host}`),'http:'),false);
  assert.equal(canConnectService(new URL('http://192.168.1.2'),'https:'),false);
  assert.equal(canConnectService(new URL('https://app.example'),'https:'),true);
});
