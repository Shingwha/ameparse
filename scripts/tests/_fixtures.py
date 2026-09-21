"""合成 .ame / .c / .cir 构造器（原 test_synthetic.py 的 fixture 数据）。

覆盖：未转义表达式（&&/<）、超级组件嵌套、隐藏变量、DIRECT 直连线、
共享槽位编译态、研究参数、Simulink 接口。
"""

from __future__ import annotations

import io
import tarfile


def _comp(alias, name, sub_name, instance, ports, params, evars, ivars, extra=""):
    port_xml = "".join(
        f"""<COMP_PORT>
      <PORT_POS>{p[1]}</PORT_POS>
      <PORT_FACE>0</PORT_FACE>
      <PORT_TYPE>{p[2]}</PORT_TYPE>
      <PORT_NAME>{p[3]}</PORT_NAME>
      <PORT_CONNECT>{p[4]}</PORT_CONNECT>
      {p[5]}
     </COMP_PORT>"""
        for p in ports
    )
    rparams = "".join(params)
    evars_xml = "".join(evars)
    ivars_xml = "".join(ivars)
    return f"""   <COMP>
    <COMP_TYPE>0</COMP_TYPE>
    <ALIAS>{alias}</ALIAS>
    <COMP_NAME>{name}</COMP_NAME>
    <COMP_DISPLAYNAME>{alias}</COMP_DISPLAYNAME>
    <COMP_ICON_DESCRIPTION>{name}</COMP_ICON_DESCRIPTION>
    <COMP_LIBRARY_ID>lib.{name}</COMP_LIBRARY_ID>
    <COMP_POS>10 20</COMP_POS>
    <COMP_DEPTH>201</COMP_DEPTH>
    <COMP_PORTS_LIST>
{port_xml}
    </COMP_PORTS_LIST>
    <LABEL_POS>0 0 0 0</LABEL_POS>
    <LABEL_VISIBLE>0</LABEL_VISIBLE>
    <CIRCUIT_SCOPE_ID>5</CIRCUIT_SCOPE_ID>
    <SUBMODEL>
     <CODE_GEN_VERSION>1.0</CODE_GEN_VERSION>
     <SUB_TYPE>0</SUB_TYPE>
     <SUB_NAME>{sub_name}</SUB_NAME>
     <SUB_DIR>$AME/lib</SUB_DIR>
     <SUB_ID_MAX>10</SUB_ID_MAX>
     <AUTONOMOUS_COMPILATION>False</AUTONOMOUS_COMPILATION>
     <AUTONOMOUS_RUNTIME>False</AUTONOMOUS_RUNTIME>
     <SUB_LABEL>{sub_name}</SUB_LABEL>
     <SUB_UNIT>{instance}</SUB_UNIT>
     <OUTPUT_TYPE>1</OUTPUT_TYPE>
     <RPARAMS_LIST>
{rparams}
     </RPARAMS_LIST>
     <EVARS_LIST>
{evars_xml}
     </EVARS_LIST>
     <IVARS_LIST>
{ivars_xml}
     </IVARS_LIST>
    </SUBMODEL>
{extra}
   </COMP>"""


CIR = f"""<?xml version="1.0" encoding="ISO-8859-1"?>
<!DOCTYPE CIR>
<CIR DOC_VERSION="2" AME_VERSION="2410" MAJ="20242" UPDATE="0" HOTFIX="0">

 <CIRCUIT>
  <CIRCUIT_HIGHEST_ID>12</CIRCUIT_HIGHEST_ID>
  <AME_APPLICATION>AMESim</AME_APPLICATION>
  <COMPS_LIST>
{_comp(
        "pump01", "PUMP00", "PUROT00", 1,
        ports=[("PORT_POS", "1 1", "hyd", "in", 1,
                "<CONNECT_LIST><CONNECT><CONNECT_ENTITY_NUM>2</CONNECT_ENTITY_NUM>"
                "<CONNECT_ENTITY_PORT>0</CONNECT_ENTITY_PORT></CONNECT></CONNECT_LIST>")],
        params=["""      <RPARAM>
       <SUB_ID>1</SUB_ID>
       <TITLE>displacement</TITLE>
       <CIRCUIT_SCOPE_ID>6</CIRCUIT_SCOPE_ID>
       <VARNAME>displ</VARNAME>
       <VISIBILITY>(mode == 1) && (sub == 2)</VISIBILITY>
       <DEF_VALUE>5.00000000000000e+01</DEF_VALUE>
       <VALUE>7.10000000000000e+01</VALUE>
       <MIN_VALUE>0</MIN_VALUE>
       <MAX_VALUE>1.00000000000000e+30</MAX_VALUE>
       <UNITS>cc/rev</UNITS>
      </RPARAM>"""],
        evars=["""      <PORT>
       <PORT_TAG>hyd</PORT_TAG>
       <EVAR>
        <SUB_ID>3</SUB_ID>
        <TITLE>flow rate at port 1</TITLE>
        <VARNAME>q1</VARNAME>
        <VISIBILITY>True</VISIBILITY>
        <TYPE>0</TYPE>
        <SAVE_VALUE>1</SAVE_VALUE>
        <UNITS>L/min</UNITS>
       </EVAR>
      </PORT>"""],
        ivars=["""      <IVAR>
       <SUB_ID>4</SUB_ID>
       <TITLE>shaft speed</TITLE>
       <VARNAME>w</VARNAME>
       <VARNAME2>dw</VARNAME2>
       <VISIBILITY>True</VISIBILITY>
       <TYPE>1</TYPE>
       <SAVE_VALUE>1</SAVE_VALUE>
       <DIMENSION>1</DIMENSION>
       <UNITS>rev/min</UNITS>
       <VALUE>0</VALUE>
      </IVAR>"""],
    )}
{_comp(
        "source2", "SOURCE00", "SOUROT00", 2,
        ports=[("PORT_POS", "1 1", "hyd", "out", 1,
                "<CONNECT_LIST><CONNECT><CONNECT_ENTITY_NUM>2</CONNECT_ENTITY_NUM>"
                "<CONNECT_ENTITY_PORT>1</CONNECT_ENTITY_PORT></CONNECT></CONNECT_LIST>")],
        params=["""      <RPARAM>
       <SUB_ID>1</SUB_ID>
       <TITLE>pressure</TITLE>
       <CIRCUIT_SCOPE_ID>6</CIRCUIT_SCOPE_ID>
       <VARNAME>p</VARNAME>
       <VISIBILITY>True</VISIBILITY>
       <DEF_VALUE>1.00000000000000e+02</DEF_VALUE>
       <VALUE>(x<=0)*10+(0<x)*20</VALUE>
       <MIN_VALUE>0</MIN_VALUE>
       <MAX_VALUE>1.00000000000000e+30</MAX_VALUE>
       <UNITS>bar</UNITS>
      </RPARAM>"""],
        evars=["""      <PORT>
       <PORT_TAG>hyd</PORT_TAG>
       <EVAR>
        <SUB_ID>9</SUB_ID>
        <TITLE>pressure at port 1</TITLE>
        <VARNAME>pout</VARNAME>
        <VISIBILITY>True</VISIBILITY>
        <TYPE>0</TYPE>
        <SAVE_VALUE>1</SAVE_VALUE>
        <UNITS>bar</UNITS>
       </EVAR>
      </PORT>"""], ivars=[""],
        extra="""    <SUPERCOMPONENT>
     <SC_LOCAL>1</SC_LOCAL>
     <CATNAME>local_category</CATNAME>
     <SC_TYPE>7</SC_TYPE>
     <SC_PORTS_MAP_LIST>
      <SC_PORT_MAP>1 0 2 1 signal 0.000000 0.000000</SC_PORT_MAP>
     </SC_PORTS_MAP_LIST>
     <CIRCUIT>
      <AME_APPLICATION>AMESim</AME_APPLICATION>
      <COMPS_LIST>
""" + _comp(
            "inner3", "GAIN00", "GA00", 3,
            ports=[("PORT_POS", "1 1", "signal", "in", 1, "")],
            params=["""      <RPARAM>
       <SUB_ID>1</SUB_ID>
       <TITLE>gain</TITLE>
       <CIRCUIT_SCOPE_ID>6</CIRCUIT_SCOPE_ID>
       <VARNAME>k</VARNAME>
       <VISIBILITY>True</VISIBILITY>
       <DEF_VALUE>1</DEF_VALUE>
       <VALUE>3.00000000000000e+00</VALUE>
       <MIN_VALUE>0</MIN_VALUE>
       <MAX_VALUE>1.00000000000000e+30</MAX_VALUE>
      </RPARAM>"""],
            evars=[""], ivars=[""],
        ) + """      </COMPS_LIST>
     </CIRCUIT>
    </SUPERCOMPONENT>""",
    )}
  </COMPS_LIST>
  <LINES_LIST>
   <LINE>
    <ALIAS>hyd_line</ALIAS>
    <LINE_TYPE>0</LINE_TYPE>
    <CIRCUIT_SCOPE_ID>8</CIRCUIT_SCOPE_ID>
    <LINE_POINTS>10,10 20,20</LINE_POINTS>
    <LINE_START_TYPE>0</LINE_START_TYPE>
    <LINE_END_TYPE>0</LINE_END_TYPE>
    <LINE_START_ENTITY>1</LINE_START_ENTITY>
    <LINE_START_PORT>1</LINE_START_PORT>
    <LINE_END_ENTITY>2</LINE_END_ENTITY>
    <LINE_END_PORT>1</LINE_END_PORT>
    <LABEL_POS>0 0 0 0</LABEL_POS>
    <LABEL_VISIBLE>0</LABEL_VISIBLE>
    <SUBMODEL>
     <CODE_GEN_VERSION>1.0</CODE_GEN_VERSION>
     <SUB_TYPE>0</SUB_TYPE>
     <SUB_NAME>DIRECT</SUB_NAME>
     <SUB_ID_MAX>4</SUB_ID_MAX>
     <SUB_LABEL>Direct connection</SUB_LABEL>
     <SUB_UNIT>0</SUB_UNIT>
     <OUTPUT_TYPE>1</OUTPUT_TYPE>
     <EVARS_LIST/>
    </SUBMODEL>
   </LINE>
  </LINES_LIST>
  <GLOBAL_PARAMS_LIST/>
 </CIRCUIT>
</CIR>
"""

PARAM = """PUROT00 instance 1 displacement [cc/rev] Is_Delta=0 Param_Id=1 Recompile_Flag=0 Data_Path=displ@pump01
PUROT00 instance 1 number of ports Param_Id=2 Recompile_Flag=0 Data_Path=nports@pump01
SOUROT00 instance 2 pressure [bar] Is_Delta=0 Param_Id=5 Recompile_Flag=0 Data_Path=p@source2
GA00 instance 3 gain [null] Is_Delta=0 Param_Id=7 Recompile_Flag=0 Data_Path=k@inner3
"""

VAR = """PUROT00 instance 1 flow rate at port 1 [L/min] Data_Path=q1@pump01
HIDDEN
PUROT00 instance 1 shaft speed [rev/min] Data_Path=w@pump01
"""

SSF = """1 PUROT00 instance 1 flow rate at port 1 [L/min] Param_Id=3 Data_Path=q1@pump01
"""

MODELINFO = """<MODEL_INFO
NUM_STATES 2
NUM_DISCRETE_STATES 0
IS_EXPLICIT 1
INTERFACE "AMESim"
>MODEL_INFO
<MODEL_OUTPUT
NUM_OUTPUT 1
OUTPUT 1 ; "Veh_Velocity" ; "Veh_Velocity@amesim_interface"
>MODEL_OUTPUT
<MODEL_INPUT
NUM_INPUT 1
INPUT 1 ; "Eng_TqCmd" ; "Eng_TqCmd@amesim_interface" ; "0.00000000000000e+00"
>MODEL_INPUT
"""

# RGL 类模型：无 INTERFACE 字段（无外部接口的纯模型）
MODELINFO_NO_IFACE = """<MODEL_INFO
NUM_STATES 252
NUM_DISCRETE_STATES 154
IS_EXPLICIT 1
>MODEL_INFO
"""

AMEGP = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE GP>
<GLOBAL_PARAMS_LIST>
 <GPARAM>
  <VARNAME>gconst</VARNAME>
  <TITLE>global constant</TITLE>
  <VALUE>9.81</VALUE>
  <UNITS>m/s2</UNITS>
 </GPARAM>
</GLOBAL_PARAMS_LIST>
"""

SIM = "0 40000 1 1e+30 1e-07 0.001 1 0.1\n0 0 0 0 8 0 0 0 0 0\n"

# 假 .c（编译产物）：pump01 的 q1 与 source2 的 pout 共享 v 槽位 5（直连）
FAKE_C = """/* fake */
// variable q1 (Basic var)
static const int EVIA_V0[7] = {5, -1, 0, -1, 1, 1, 1};
// variable pout (Basic var)
static const int EVIA_V1[7] = {5, -1, 1, -1, 1, 1, 1};
static const int* EVIA[2] = {
     EVIA_V0, EVIA_V1
};
static const S_AMEModelSubInfo SUBSTRUC[2] = {
     { {1, &EVIA[0], NULL, PVIA, NULL, NULL, NULL, NULL}, {{0, 0}}, "PUROT00", 1, NULL }
   , { {1, &EVIA[1], NULL, PVIA, NULL, NULL, NULL, NULL}, {{0, 0}}, "SOUROT00", 2, NULL }
};
static int v[16];
"""

STUDYPARAM = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE STUDY>
<STUDY DOC_VERSION="2" AME_VERSION="2410" MAJ="20242" UPDATE="0" HOTFIX="0">
 <INPUT_LIST>
  <STUDY_PARAM>
   <STUDY_PARAM_NAME>displ__pump01</STUDY_PARAM_NAME>
   <VALUE>71</VALUE>
   <UPPER_BOUND>100</UPPER_BOUND>
   <LOWER_BOUND>0</LOWER_BOUND>
   <ORIGIN>Submodel global</ORIGIN>
   <PARAM_TYPE>Real</PARAM_TYPE>
   <AMESIM_NAME>displ</AMESIM_NAME>
   <TITLE>displacement</TITLE>
   <SUB_NAME>PUROT00</SUB_NAME>
   <INSTANCE>1</INSTANCE>
   <ALIAS_PATH>pump01 [PUROT00-1]</ALIAS_PATH>
  </STUDY_PARAM>
 </INPUT_LIST>
 <BATCH_STUDY>
  <BATCH_PARAMS>
   <PARAM>
    <PARAM_USED>0</PARAM_USED>
    <PARAM_NAME>displ@pump01</PARAM_NAME>
    <PARAM_UNIT>cc/rev</PARAM_UNIT>
    <RANGE_VALUE>71</RANGE_VALUE>
    <SET_VALUE>50</SET_VALUE>
    <SET_VALUE>100</SET_VALUE>
   </PARAM>
  </BATCH_PARAMS>
 </BATCH_STUDY>
</STUDY>
"""

UNITS = """<?xml version="1.0" encoding="UTF-8"?>
<Unit_Configurations Active_Configuration_Id="1">
 <Configuration_Definition Name="SI">
  <Domain_Definition Name="length"/>
 </Configuration_Definition>
 <Unit_Definition Name="m"/>
</Unit_Configurations>
"""

PROPERTIES = """<?xml version="1.0" encoding="UTF-8"?>
<properties>
 <property id="p1" name="author" target="model"/>
</properties>
"""


def make_ame_bytes(model: str = "TestModel") -> bytes:
    members = {
        f"{model}_.cir": CIR.encode("latin-1"),
        f"{model}_.param": PARAM.encode("latin-1"),
        f"{model}_.var": VAR.encode("latin-1"),
        f"{model}_.ssf": SSF.encode("latin-1"),
        f"{model}_.modelinfo": MODELINFO.encode("latin-1"),
        f"{model}_.amegp": AMEGP.encode("latin-1"),
        f"{model}_.sim": SIM.encode("latin-1"),
        f"{model}_.studyparam": STUDYPARAM.encode("latin-1"),
        f"{model}_.units": UNITS.encode("latin-1"),
        f"{model}_.props/properties.xml": PROPERTIES.encode("latin-1"),
        f"{model}_.results": b"\x00" * 64,
        f"{model}_.c": FAKE_C.encode("latin-1"),
    }
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def make_ame(path, model: str = "TestModel") -> str:
    with open(path, "wb") as f:
        f.write(make_ame_bytes(model))
    return str(path)
