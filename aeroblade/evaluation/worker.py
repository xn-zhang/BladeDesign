"""Isolated numeric process. Only the authenticated bridge creates requests."""
import argparse,json,pathlib,re
from .data import export_dataset,evaluate_job,write_json
from .regression import train,predict

def child(root,kind,identifier,length=24):
    if not isinstance(identifier,str) or not re.fullmatch('[a-f0-9]{'+str(length)+'}',identifier):raise ValueError('无效记录标识')
    p=root/kind/identifier
    if p.is_symlink() or not p.resolve().is_relative_to(root.resolve()):raise ValueError('记录路径越界')
    return p

def execute(req):
    root=pathlib.Path(req['root']);jobs=pathlib.Path(req['jobs']);p=req['payload'];kind=req['kind']
    if kind in ('batch_generate','batch_import'):
        from .batch_data import generate,import_designs
        return generate(p['plan'],root) if kind=='batch_generate' else import_designs(p['bundle'],root)
    if kind=='dataset':return export_dataset(jobs,root,p.get('selection'))
    if kind=='train':return train(child(root,'datasets',p['dataset_id'])/'manifest.json',root,p.get('algorithm','ridge'),p.get('seed',42))
    if kind=='predict':return predict(child(root,'models',p['model_id']),p['parameters'],p['conditions'])
    if kind=='predict_batch':
        if not isinstance(p['parameters'],list) or len(p['parameters'])>200:raise ValueError('批量预测最多200个候选')
        results=[]
        for parameters in p['parameters']:
            try:results.append(predict(child(root,'models',p['model_id']),parameters,p['conditions']))
            except (ValueError,KeyError) as e:results.append({'error':str(e)})
        return results
    if kind=='analyze':
        folder=child(jobs.parent,jobs.name,p['job_id'],32);record,_=evaluate_job(folder);return record
    if kind=='geometry':
        from .data import geometry
        return geometry(p['parameters'])
    raise ValueError('未知计算类型')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--request',required=True);parser.add_argument('--result',required=True);args=parser.parse_args()
    try:result={'ok':True,'result':execute(json.loads(pathlib.Path(args.request).read_text(encoding='utf-8')))}
    except Exception as e:result={'ok':False,'error':str(e)[:1800] or type(e).__name__}
    write_json(args.result,result)

if __name__=='__main__':main()
