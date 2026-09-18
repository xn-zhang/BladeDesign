"""Pritchard input boundary and deterministic, geometry-derived cascade domain."""
import math
RANGES={'radius':(30,1000),'bladeCount':(10,200),'axialChord':(10,100),'tangentialChord':(-60,100),
        'throat':(.5,80),'leadingRadius':(.1,6),'trailingRadius':(.05,3),'inletAngle':(-60,70),
        'outletAngle':(-80,-5),'inletHalfWedge':(1,25),'unguidedTurning':(.1,40),'height':(30,160)}
def validate_parameters(p):
    if set(p)!=set(RANGES)|{'model'} or p.get('model')!='pritchard-1985':raise ValueError('Pritchard参数字段不匹配')
    for key,(lo,hi) in RANGES.items():
        v=p[key]
        if type(v) not in (int,float) or not math.isfinite(v) or not lo<=v<=hi:raise ValueError('Pritchard参数超出范围: '+key)
    if int(p['bladeCount'])!=p['bladeCount']:raise ValueError('叶片数必须是整数')
    return p.copy()
def mesh_tokens(p):
    validate_parameters(p)
    cx=p['axialChord']*.001;ct=p['tangentialChord']*.001;s=2*math.pi*p['radius']/p['bladeCount']*.001
    xlo=-2*cx;xhi=3*cx;slope=-ct/cx
    # Parallel periodic boundaries follow the chord-line shear, translating by pitch.
    values={'PC_XLO':xlo,'PC_XHI':xhi,'PC_YLL':slope*xlo-s/2,'PC_YLH':slope*xlo+s/2,
            'PC_YHL':slope*xhi-s/2,'PC_YHH':slope*xhi+s/2,'PC_PITCH':s,'PC_NEG_PITCH':-s,
            'PC_SEED_X':-math.sqrt(2)*cx,'PC_SEED_Y':slope*(-math.sqrt(2)*cx)+.127*s}
    return {k:format(v,'.15g') for k,v in values.items()}
