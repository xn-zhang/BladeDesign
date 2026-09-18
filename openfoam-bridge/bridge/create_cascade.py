"""Generate a cold periodic cascade for OpenCFD v2512; not an engineering benchmark."""
import argparse,json,pathlib,re
ROOT=pathlib.Path(__file__).resolve().parents[1]
PARAMETERS=dict(chord=40,thickness=12,position=35,inlet=10,outlet=-5,stagger=0,height=60,taper=1,twist=0,sweep=0,lean=0)
def create(target):
    target=pathlib.Path(target)
    if target.exists():raise FileExistsError('Refusing to overwrite '+str(target))
    target.mkdir(parents=True)
    def write(name,body,cls='dictionary'):
        p=target/name;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(f'FoamFile {{version 2.0; format ascii; class {cls}; object {p.name};}}\n'+body)
    write('system/blockMeshDict',r'''
scale 1;
vertices ((-0.06 -0.03 -0.005) (0.10 -0.03 -0.005) (0.10 0.03 -0.005) (-0.06 0.03 -0.005)
          (-0.06 -0.03 0.005) (0.10 -0.03 0.005) (0.10 0.03 0.005) (-0.06 0.03 0.005));
blocks (hex (0 1 2 3 4 5 6 7) (80 30 5) simpleGrading (1 1 1)); edges ();
boundary (
 inlet {type patch; faces ((0 4 7 3));} outlet {type patch; faces ((1 2 6 5));}
 periodicLow {type cyclic; neighbourPatch periodicHigh; transform translational; separationVector (0 0.06 0); faces ((0 1 5 4));}
 periodicHigh {type cyclic; neighbourPatch periodicLow; transform translational; separationVector (0 -0.06 0); faces ((3 7 6 2));}
 spanLow {type symmetryPlane; faces ((0 3 2 1));} spanHigh {type symmetryPlane; faces ((4 5 6 7));}
); mergePatchPairs ();
''')
    write('system/snappyHexMeshDict',r'''
castellatedMesh true; snap true; addLayers false;
geometry {blade.stl {type triSurfaceMesh; name blade;}}
castellatedMeshControls {
 maxLocalCells 500000; maxGlobalCells 500000; minRefinementCells 0; maxLoadUnbalance 0.1;
 nCellsBetweenLevels 3; resolveFeatureAngle 30; features ();
 refinementSurfaces {blade {level (2 3); patchInfo {type wall;}}}
 refinementRegions {} locationInMesh (-0.05 0 0); allowFreeStandingZoneFaces true;
}
snapControls {nSmoothPatch 3; tolerance 2; nSolveIter 40; nRelaxIter 5; nFeatureSnapIter 10;
 implicitFeatureSnap true; explicitFeatureSnap false; multiRegionFeatureSnap false;}
addLayersControls {
 relativeSizes true; layers {}; expansionRatio 1.2; finalLayerThickness 0.3; minThickness 0.1;
 nGrow 0; featureAngle 60; nRelaxIter 5; nSmoothSurfaceNormals 1; nSmoothNormals 3;
 nSmoothThickness 10; maxFaceThicknessRatio 0.5; maxThicknessToMedialRatio 0.3;
 minMedialAxisAngle 90; nBufferCellsNoExtrude 0; nLayerIter 50;
}
meshQualityControls {
 maxNonOrtho 65; maxBoundarySkewness 20; maxInternalSkewness 4; maxConcave 80;
 minVol 1e-16; minTetQuality 1e-30; minArea -1; minTwist 0.02; minDeterminant 0.001;
 minFaceWeight 0.05; minVolRatio 0.01; minTriangleTwist -1; nSmoothScale 4; errorReduction 0.75;
}
mergeTolerance 1e-6;
''')
    write('system/extrudeMeshDict','constructFrom patch;\nsourceCase ".";\nsourcePatches (spanLow);\nexposedPatchName spanHigh;\nflipNormals true;\nextrudeModel plane;\nnLayers 1;\nexpansionRatio 1;\nplaneCoeffs {thickness 0.01;}\nmergeFaces false;\nmergeTol 0;\n\nthickness 0.01;\n')
    write('system/createPatchDict','pointSync true;\npatches (\n{name cyclicLow; patchInfo {type cyclic; neighbourPatch cyclicHigh; transform translational; separationVector (0 0.06 0);} constructFrom patches; patches (periodicLow);}\n{name cyclicHigh; patchInfo {type cyclic; neighbourPatch cyclicLow; transform translational; separationVector (0 -0.06 0);} constructFrom patches; patches (periodicHigh);}\n);\n')
    quality=re.search(r'meshQualityControls\s*\{([^}]+)\}',(target/'system/snappyHexMeshDict').read_text()).group(1)
    write('system/meshQualityDict',quality)
    write('constant/thermophysicalProperties',r'''
thermoType {type hePsiThermo; mixture pureMixture; transport const; thermo hConst;
 equationOfState perfectGas; specie specie; energy sensibleEnthalpy;}
mixture {specie {molWeight 28.96;} thermodynamics {Cp 1004.5; Hf 0;} transport {mu 1.8e-05; Pr 0.7;}}
''')
    write('constant/turbulenceProperties','simulationType RAS;\nRAS {RASModel kOmegaSST; turbulence on; printCoeffs on;}\n')
    write('system/fvSchemes',r'''
ddtSchemes {default steadyState;}
gradSchemes {default cellLimited Gauss linear 1;}
divSchemes {default none; div(phi,U) bounded Gauss upwind; div(phi,h) bounded Gauss upwind;
 div(phi,K) bounded Gauss upwind; div(phi,k) bounded Gauss upwind; div(phi,omega) bounded Gauss upwind;
 div(phid,p) Gauss upwind; div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;}
laplacianSchemes {default Gauss linear limited 0.5;}
interpolationSchemes {default linear;} snGradSchemes {default limited 0.5;}
wallDist {method meshWave;} fluxRequired {default no; p;}
''')
    write('system/fvSolution',r'''
solvers {
 p {solver GAMG; tolerance 1e-9; relTol 0; maxIter 100; smoother GaussSeidel;}
 "(U|h|k|omega)" {solver smoothSolver; smoother symGaussSeidel; tolerance 1e-10; relTol 0;}
 rho {solver diagonal;}
}
SIMPLE {nNonOrthogonalCorrectors 2; consistent no;
 residualControl {p 1e-5; U 1e-5; h 1e-5; k 1e-5; omega 1e-5;}}
relaxationFactors {fields {p 0.15; rho 0.15;} equations {U 0.3; h 0.5; k 0.5; omega 0.5;}}
''')
    write('system/controlDict',r'''
application rhoSimpleFoam;
startFrom startTime; startTime 0; stopAt endTime; endTime {{ITERATIONS}};
deltaT 1; writeControl timeStep; writeInterval 100; purgeWrite 2;
writeFormat ascii; writePrecision 10; writeCompression off;
timeFormat general; timePrecision 8; runTimeModifiable false;
functions {
 inletMassFlow {type surfaceFieldValue; libs ("libfieldFunctionObjects.so"); regionType patch;
 name inlet; operation sum; fields (phi); writeFields false; writeControl timeStep; writeInterval 1; log true;}
 outletMassFlow {type surfaceFieldValue; libs ("libfieldFunctionObjects.so"); regionType patch;
 name outlet; operation sum; fields (phi); writeFields false; writeControl timeStep; writeInterval 1; log true;}
 yPlus {type yPlus; libs ("libfieldFunctionObjects.so"); writeControl writeTime;}
}
''')
    common='cyclicLow {type cyclic;} cyclicHigh {type cyclic;} spanLow {type empty;} spanHigh {type empty;}'
    fields={
      'U':('volVectorField','0 1 -1 0 0 0 0','(18 0 0)',r'inlet {type pressureInletOutletVelocity; value uniform (18 0 0);} outlet {type inletOutlet; inletValue uniform (18 0 0); value uniform (18 0 0);} blade {type noSlip;}'),
      'p':('volScalarField','1 -1 -2 0 0 0 0','{{OUTLET_STATIC_PRESSURE_PA}}',r'inlet {type totalPressure; p0 uniform {{INLET_TOTAL_PRESSURE_PA}}; gamma 1.4; psi thermo:psi; rho none; value uniform {{INLET_TOTAL_PRESSURE_PA}};} outlet {type fixedValue; value uniform {{OUTLET_STATIC_PRESSURE_PA}};} blade {type zeroGradient;}'),
      'T':('volScalarField','0 0 0 1 0 0 0','{{INLET_TOTAL_TEMPERATURE_K}}',r'inlet {type totalTemperature; T0 uniform {{INLET_TOTAL_TEMPERATURE_K}}; gamma 1.4; psi thermo:psi; value uniform {{INLET_TOTAL_TEMPERATURE_K}};} outlet {type inletOutlet; inletValue uniform {{INLET_TOTAL_TEMPERATURE_K}}; value uniform {{INLET_TOTAL_TEMPERATURE_K}};} blade {type zeroGradient;}'),
      'k':('volScalarField','0 2 -2 0 0 0 0','0.5',r'inlet {type fixedValue; value uniform 0.5;} outlet {type inletOutlet; inletValue uniform 0.5; value uniform 0.5;} blade {type kqRWallFunction; value uniform 0.5;}'),
      'omega':('volScalarField','0 0 -1 0 0 0 0','500',r'inlet {type fixedValue; value uniform 500;} outlet {type inletOutlet; inletValue uniform 500; value uniform 500;} blade {type omegaWallFunction; value uniform 500;}'),
      'nut':('volScalarField','0 2 -1 0 0 0 0','0',r'inlet {type calculated; value uniform 0;} outlet {type calculated; value uniform 0;} blade {type nutkWallFunction; value uniform 0;}'),
      'alphat':('volScalarField','1 -1 -1 0 0 0 0','0',r'inlet {type calculated; value uniform 0;} outlet {type calculated; value uniform 0;} blade {type compressible::alphatWallFunction; Prt 0.85; value uniform 0;}')}
    for name,(cls,dim,value,bc) in fields.items():write('0/'+name,f'dimensions [{dim}];\ninternalField uniform {value};\nboundaryField {{ {common} {bc} }}\n',cls)
    inputs=[dict(key='inletTotalPressure',label='入口总压',unit='Pa',min=100100,max=100500,default=100200,token='INLET_TOTAL_PRESSURE_PA'),
      dict(key='inletTotalTemperature',label='入口总温',unit='K',min=290,max=310,default=300,token='INLET_TOTAL_TEMPERATURE_K'),
      dict(key='outletStaticPressure',label='出口静压',unit='Pa',min=100000,max=100000,default=100000,token='OUTLET_STATIC_PRESSURE_PA'),
      dict(key='iterations',label='迭代上限',unit='',min=100,max=5000,default=3000,integer=True,token='ITERATIONS')]
    manifest=dict(id='cold-periodic-cascade-2d',name='二维冷态周期叶栅 · 流程验证',description='OpenCFD v2512 / SST / 60 mm 节距 / 10 mm 参考展宽 / 二维 empty 边界。等截面直叶片；无棱柱层，非工程损失或效率验证。',solver='rhoSimpleFoam',geometry_file='constant/triSurface/blade.stl',geometry_bounds_m=[[-.035,-.015,-.08],[.035,.015,.08]],inputs=inputs,constraints=[dict(left='inletTotalPressure',op='>',right='outletStaticPressure')],pipeline=[['blockMesh'],['snappyHexMesh','-overwrite'],['extrudeMesh'],['createPatch','-overwrite'],['checkMesh','-allTopology','-meshQuality'],['rhoSimpleFoam'],['foamToVTK','-latestTime']],parameter_bounds=dict(taper=[1,1],twist=[0,0],sweep=[0,0],lean=[0,0]),recommended_parameters=PARAMETERS)
    (target/'aeroblade-template.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    request=dict(schema='aeroblade-cfd-v1',template_id=manifest['id'],parameters=PARAMETERS,conditions={i['key']:i['default'] for i in inputs})
    (target/'recommended-request.json').write_text(json.dumps(request,ensure_ascii=False,indent=2))
    return request
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--target',type=pathlib.Path,default=ROOT/'templates/cold-periodic-cascade-2d');args=parser.parse_args()
    create(args.target);print(args.target)
# end
