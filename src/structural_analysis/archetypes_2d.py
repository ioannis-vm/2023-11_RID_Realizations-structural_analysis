"""
Equivalent 2D models of the archetypes considered in this study.

"""

from copy import deepcopy
import numpy as np
from osmg.model import Model
from osmg.gen.component_gen import BeamColumnGenerator
from osmg.gen.component_gen import TrussBarGenerator
from osmg.gen.section_gen import SectionGenerator
from osmg.gen.material_gen import MaterialGenerator
from osmg import defaults
from osmg.preprocessing.self_weight_mass import self_weight
from osmg.preprocessing.self_weight_mass import self_mass
from osmg.ops.section import ElasticSection
from osmg.ops.section import FiberSection
from osmg.ops.element import ElasticBeamColumn
from osmg.ops.element import DispBeamColumn
from osmg.ops.element import TwoNodeLink
from osmg.gen.query import ElmQuery
from osmg.gen.zerolength_gen import imk_56
from osmg.gen.zerolength_gen import imk_6
from osmg.load_case import LoadCase
from osmg.common import G_CONST_IMPERIAL
from osmg.ops.uniaxial_material import Elastic
from osmg.gen.mesh_shapes import rect_mesh
from osmg.gen.zerolength_gen import gravity_shear_tab
from osmg.gen.zerolength_gen import steel_brace_gusset
from osmg.ops.uniaxial_material import Steel02

# pylint:disable=too-many-locals
# pylint:disable=too-many-branches
# pylint:disable=too-many-statements
# pylint:disable=too-many-arguments
# pylint:disable=too-many-lines
# pylint:disable=consider-using-enumerate
# pylint:disable=use-dict-literal


def generate_archetype(
    level_elevs,
    sections,
    metadata,
    archetype,
    grav_bm_moment_mod,
    grav_col_moment_mod_interior,
    grav_col_moment_mod_exterior,
    lvl_weight,
    beam_udls,
    no_diaphragm=False,
):
    """
    Generate a 2D model of an archetype.

    Arguments:
      sections:
          Dictionary containing the names of the sections used.
      metadata:
          Dictionary containing additional information, depending on
          the archetype.
      archetype:
          Code name of the archetype, e.g. smrf_3_ii represents a
          3-story risk category ii SMRF structure (with an office
          occupancy, even though all considered occupancies use the
          same structural analysis results in this study).
      grav_bm_moment_mod:
          Moment modification factor, used to amplify the moments of
          the gravity beams to lump the effect of all of the gravity
          beams in one element.
      grav_col_moment_mod_interior:
          Similar to grav_bm_moment_mod
      grav_col_moment_mod_exterior:
          Similar to grav_bm_moment_mod
      lvl_weight:
          Dictionary containing the weight of each story.
      beam_udls:
          Dictionary containing the uniformly distributed load applied
          to the lateral framing beams.
      no_diaphragm:
          If True, no diaphragm constraints are assigned.

    """

    n_parameter = 10.00

    lateral_system, num_levels_str, risk_category = archetype.split("_")
    num_levels = int(num_levels_str)

    # define the model
    mdl = Model("model")
    bcg = BeamColumnGenerator(mdl)
    secg = SectionGenerator(mdl)
    mtlg = MaterialGenerator(mdl)
    query = ElmQuery(mdl)
    trg = TrussBarGenerator(mdl)

    mdl.add_level(0, 0.00)
    for i, height in enumerate(level_elevs):
        mdl.add_level(i + 1, height)

    level_elevs = []
    for level in mdl.levels.values():
        level_elevs.append(level.elevation)
    level_elevs = np.diff(level_elevs)

    defaults.load_default_steel(mdl)
    defaults.load_default_fix_release(mdl)
    defaults.load_util_rigid_elastic(mdl)
    # also add a material with an fy of 46 ksi for the SCBFs
    uniaxial_mat = Steel02(
        mdl.uid_generator.new("uniaxial material"),
        "brace steel",
        46000.00,
        29000000.00,
        11153846.15,
        0.01,
        15.0,
        0.925,
        0.15,
    )
    mdl.uniaxial_materials.add(uniaxial_mat)

    steel_phys_mat = mdl.physical_materials.retrieve_by_attr("name", "default steel")

    def flatten_dict(dictionary):
        vals = []
        for value in dictionary.values():
            if isinstance(value, dict):
                # recursively flatten the nested dictionary
                vals.extend(flatten_dict(value))
            else:
                vals.append(value)
        return vals

    wsections = set()
    hss_secs = set()
    for val in flatten_dict(sections):
        if val.startswith("W"):
            wsections.add(val)
        elif val.startswith("H"):
            hss_secs.add(val)
        # else, it's probably a BRB area

    section_type = ElasticSection
    element_type = ElasticBeamColumn
    sec_collection = mdl.elastic_sections

    for sec in wsections:
        secg.load_aisc_from_database(
            "W", [sec], "default steel", "default steel", section_type
        )
    for sec in hss_secs:
        secg.load_aisc_from_database(
            "HSS_circ", [sec], "brace steel", "default steel", FiberSection
        )

    x_grd_tags = ["LC", "G1", "G2", "1", "2", "3", "4", "5", "6", "7", "8"]
    x_grd_locs = np.linspace(
        0.00, len(x_grd_tags) * 25.00 * 12.00, len(x_grd_tags) + 1
    )
    x_grd = {x_grd_tags[i]: x_grd_locs[i] for i in range(len(x_grd_tags))}

    n_sub = 1  # linear elastic element subdivision

    col_gtransf = "Corotational"

    # add the lateral system

    brace_lens = metadata["brace_buckling_length"]
    brace_l_c = metadata["brace_l_c"]
    gusset_t_p = metadata["gusset_t_p"]
    gusset_avg_buckl_len = metadata["gusset_avg_buckl_len"]
    hinge_dist = metadata["hinge_dist"]

    plate_a = metadata["plate_a"]
    plate_b = metadata["plate_b"]

    sec = sec_collection.retrieve_by_attr(
        "name", sections["lateral_beams"]["level_1"]
    )
    vertical_offsets = [-sec.properties["d"] / 2.00]
    for level_counter in range(num_levels):
        level_tag = f"level_{level_counter+1}"
        sec = sec_collection.retrieve_by_attr(
            "name", sections["lateral_beams"][f"level_{level_counter+1}"]
        )
        vertical_offsets.append(-sec.properties["d"] / 2.00)

    # frame columns
    for level_counter in range(num_levels):
        level_tag = f"level_{level_counter+1}"
        if level_counter % 2 == 0:
            even_story_num = False  # (odd because of zero-indexing)
        else:
            even_story_num = True
        mdl.levels.set_active([level_counter + 1])
        sec = sec_collection.retrieve_by_attr(
            "name", sections["lateral_cols"][level_tag]
        )
        sec_cp = deepcopy(sec)
        sec_cp.i_x *= (n_parameter + 1) / n_parameter
        sec_cp.i_y *= (n_parameter + 1) / n_parameter
        column_depth = sec.properties["d"]
        beam_depth = sec_collection.retrieve_by_attr(
            "name", sections["lateral_beams"][level_tag]
        ).properties["d"]
        for plcmt in ("1", "2", "3"):
            x_coord = x_grd[plcmt]
            if not even_story_num:
                if plcmt == "2":
                    continue
            else:
                if plcmt in ("1", "3"):
                    continue
            bcg.add_pz_active(
                x_coord,
                0.00,
                sec,
                steel_phys_mat,
                np.pi / 2.00,
                column_depth,
                beam_depth,
                "steel_w_col_pz_updated",
                {
                    "pz_doubler_plate_thickness": 0.00,
                    "axial_load_ratio": 0.00,
                    "slab_depth": 0.00,
                    "consider_composite": False,
                    "location": "interior",
                    "only_elastic": False,
                    "moment_modifier": 1.00,
                },
            )
        for plcmt in ("1", "2", "3"):
            x_coord = x_grd[plcmt]
            if not even_story_num:
                if plcmt == "2":
                    top_offset = -beam_depth - plate_b[level_counter + 1]
                    bot_offset = 0.00
                else:
                    top_offset = 0.00
                    bot_offset = +plate_b[level_counter + 1]
            else:
                if plcmt in ("1", "3"):
                    top_offset = -beam_depth - plate_b[level_counter + 1]
                    bot_offset = 0.00
                else:
                    top_offset = 0.00
                    bot_offset = +plate_b[level_counter + 1]
            bcg.add_vertical_active(
                x_coord,
                0.00,
                np.array((0.00, 0.00, top_offset)),
                np.array((0.00, 0.00, bot_offset)),
                col_gtransf,
                n_sub,
                sec_cp,
                element_type,
                "centroid",
                np.pi / 2.00,
                method="generate_hinged_component_assembly",
                additional_args={
                    "n_x": n_parameter,
                    "n_y": None,
                    "zerolength_gen_i": imk_6,
                    "zerolength_gen_args_i": {
                        "lboverl": 1.00,
                        "loverh": 0.50,
                        "rbs_factor": None,
                        "consider_composite": False,
                        "axial_load_ratio": 0.00,
                        "section": sec,
                        "n_parameter": n_parameter,
                        "physical_material": steel_phys_mat,
                        "distance": 0.01,
                        "n_sub": 1,
                        "element_type": TwoNodeLink,
                    },
                    "zerolength_gen_j": imk_6,
                    "zerolength_gen_args_j": {
                        "lboverl": 1.00,
                        "loverh": 0.50,
                        "rbs_factor": None,
                        "consider_composite": False,
                        "axial_load_ratio": 0.00,
                        "section": sec,
                        "n_parameter": n_parameter,
                        "physical_material": steel_phys_mat,
                        "distance": 0.01,
                        "n_sub": 1,
                        "element_type": TwoNodeLink,
                    },
                },
            )

    # frame beams
    for level_counter in range(num_levels):
        level_tag = f"level_{level_counter+1}"
        if level_counter % 2 == 0:
            even_story_num = False  # (odd because of zero-indexing)
        else:
            even_story_num = True
        mdl.levels.set_active([level_counter + 1])
        sec = sec_collection.retrieve_by_attr(
            "name", sections["lateral_beams"][level_tag]
        )
        sec_cp = deepcopy(sec)
        sec_cp.i_x *= (n_parameter + 1) / n_parameter
        sec_cp.i_y *= (n_parameter + 1) / n_parameter

        for plcmt_tag_i, plcmt_tag_j in zip(("1", "2"), ("2", "3")):
            plcmt_i = x_grd[plcmt_tag_i]
            plcmt_j = x_grd[plcmt_tag_j]
            if not even_story_num:
                if plcmt_tag_i == "1":
                    snap_i = "middle_back"
                    snap_j = "top_center"
                    offset_i = np.zeros(3)
                    offset_j = np.array(
                        (-0.75 * plate_a[level_counter + 1], 0.00, 0.00)
                    )
                else:
                    snap_i = "bottom_center"
                    snap_j = "middle_front"
                    offset_i = np.array(
                        (+0.75 * plate_a[level_counter + 1], 0.00, 0.00)
                    )
                    offset_j = np.zeros(3)
            else:
                if plcmt_tag_i == "1":
                    snap_i = "bottom_center"
                    snap_j = "middle_front"
                    offset_i = np.array(
                        (+0.75 * plate_a[level_counter + 1], 0.00, 0.00)
                    )
                    offset_j = np.zeros(3)
                else:
                    snap_i = "middle_back"
                    snap_j = "top_center"
                    offset_i = np.zeros(3)
                    offset_j = np.array(
                        (-0.75 * plate_a[level_counter + 1], 0.00, 0.00)
                    )

            bcg.add_horizontal_active(
                plcmt_i,
                0.00,
                plcmt_j,
                0.00,
                offset_i,
                offset_j,
                snap_i,
                snap_j,
                "Linear",
                1,
                sec_cp,
                element_type,
                "top_center",
                method="generate_hinged_component_assembly",
                additional_args={
                    "n_x": n_parameter,
                    "n_y": None,
                    "zerolength_gen_i": imk_6,
                    "zerolength_gen_args_i": {
                        "lboverl": 0.75,
                        "loverh": 0.50,
                        "rbs_factor": None,
                        "consider_composite": True,
                        "axial_load_ratio": 0.00,
                        "section": sec,
                        "n_parameter": n_parameter,
                        "physical_material": steel_phys_mat,
                        "distance": 0.01,
                        "n_sub": 1,
                        "element_type": TwoNodeLink,
                    },
                    "zerolength_gen_j": imk_6,
                    "zerolength_gen_args_j": {
                        "lboverl": 0.75,
                        "loverh": 0.50,
                        "rbs_factor": None,
                        "consider_composite": True,
                        "axial_load_ratio": 0.00,
                        "section": sec,
                        "n_parameter": n_parameter,
                        "physical_material": steel_phys_mat,
                        "distance": 0.01,
                        "n_sub": 1,
                        "element_type": TwoNodeLink,
                    },
                },
            )
    # braces
    brace_subdiv = 8
    for level_counter in range(num_levels):
        level_tag = f"level_{level_counter+1}"
        if level_counter % 2 == 0:
            even_story_num = False  # (odd because of zero-indexing)
        else:
            even_story_num = True
        mdl.levels.set_active([level_counter + 1])
        brace_sec_name = sections["braces"][level_tag]

        for plcmt_i, plcmt_j in zip(("2", "2"), ("1", "3")):
            if not even_story_num:
                x_i = x_grd[plcmt_i]
                x_j = x_grd[plcmt_j]
            else:
                x_i = x_grd[plcmt_j]
                x_j = x_grd[plcmt_i]

            brace_sec = mdl.fiber_sections.retrieve_by_attr("name", brace_sec_name)

            brace_phys_mat = deepcopy(steel_phys_mat)
            brace_phys_mat.f_y = 50.4 * 1000.00  # for round HSS
            brace_mat = mtlg.generate_steel_hss_circ_brace_fatigue_mat(
                brace_sec, brace_phys_mat, brace_lens[level_counter + 1]
            )

            bsec = brace_sec.copy_alter_material(
                brace_mat, mdl.uid_generator.new("section")
            )

            bcg.add_diagonal_active(
                x_i,
                0.00,
                x_j,
                0.00,
                np.array((0.00, 0.00, vertical_offsets[level_counter])),
                np.array((0.00, 0.00, vertical_offsets[level_counter])),
                "bottom_node",
                "top_node",
                "Corotational",
                brace_subdiv,
                bsec,
                DispBeamColumn,
                "centroid",
                0.00,
                0.00,
                0.1 / 100.00,
                None,
                None,
                "generate_hinged_component_assembly",
                {
                    "n_x": None,
                    "n_y": None,
                    "zerolength_gen_i": steel_brace_gusset,
                    "zerolength_gen_args_i": {
                        "distance": hinge_dist[level_counter + 1],
                        "element_type": TwoNodeLink,
                        "physical_mat": steel_phys_mat,
                        "d_brace": bsec.properties["OD"],
                        "l_c": brace_l_c[level_counter + 1],
                        "t_p": gusset_t_p[level_counter + 1],
                        "l_b": gusset_avg_buckl_len[level_counter + 1],
                    },
                    "zerolength_gen_j": steel_brace_gusset,
                    "zerolength_gen_args_j": {
                        "distance": hinge_dist[level_counter + 1],
                        "element_type": TwoNodeLink,
                        "physical_mat": steel_phys_mat,
                        "d_brace": bsec.properties["OD"],
                        "l_c": brace_l_c[level_counter + 1],
                        "t_p": gusset_t_p[level_counter + 1],
                        "l_b": gusset_avg_buckl_len[level_counter + 1],
                    },
                },
            )

    # add the gravity framing
    for level_counter in range(num_levels):
        level_tag = "level_" + str(level_counter + 1)
        mdl.levels.set_active([level_counter + 1])

        # add the columns
        for plcmt_tag in ("G1", "G2"):
            if plcmt_tag == "G1":
                placement = "interior"
                moment_mod = grav_col_moment_mod_interior
            else:
                placement = "exterior"
                moment_mod = grav_col_moment_mod_exterior
            sec = sec_collection.retrieve_by_attr(
                "name", sections["lateral_cols"][level_tag]
            )
            sec_cp = deepcopy(sec)
            sec_cp.i_x *= (
                (n_parameter + 1) / n_parameter * moment_mod * grav_bm_moment_mod
            )
            sec_cp.i_y *= (
                (n_parameter + 1) / n_parameter * moment_mod * grav_bm_moment_mod
            )
            sec_cp.area *= moment_mod
            bcg.add_vertical_active(
                x_grd[plcmt_tag],
                0.00,
                np.zeros(3),
                np.zeros(3),
                col_gtransf,
                n_sub,
                sec_cp,
                element_type,
                "centroid",
                0.00,
                method="generate_hinged_component_assembly",
                additional_args={
                    "n_x": n_parameter,
                    "n_y": n_parameter,
                    "zerolength_gen_i": None,
                    "zerolength_gen_args_i": {},
                    "zerolength_gen_j": imk_56,
                    "zerolength_gen_args_j": {
                        "lboverl": 1.00,
                        "loverh": 0.50,
                        "rbs_factor": None,
                        "consider_composite": False,
                        "axial_load_ratio": 0.00,
                        "section": sec,
                        "n_parameter": n_parameter,
                        "physical_material": steel_phys_mat,
                        "distance": 0.01,
                        "n_sub": 1,
                        "element_type": TwoNodeLink,
                        "moment_modifier": moment_mod,
                    },
                },
            )

        # add the gravity beams
        sec = sec_collection.retrieve_by_attr(
            "name", sections["gravity_beams"][level_tag]
        )
        moment_mod = grav_bm_moment_mod
        sec_cp = deepcopy(sec)
        sec_cp.i_x *= (n_parameter + 1) / n_parameter * moment_mod
        sec_cp.area *= moment_mod
        bcg.add_horizontal_active(
            x_grd["G1"],
            0.00,
            x_grd["G2"],
            0.00,
            np.array((0.0, 0.0, 0.0)),
            np.array((0.0, 0.0, 0.0)),
            "centroid",
            "centroid",
            "Linear",
            n_sub,
            sec_cp,
            element_type,
            "centroid",
            method="generate_hinged_component_assembly",
            additional_args={
                "n_x": n_parameter,
                "n_y": None,
                "zerolength_gen_i": gravity_shear_tab,
                "zerolength_gen_args_i": {
                    "consider_composite": True,
                    "section": sec,
                    "n_parameter": n_parameter,
                    "physical_material": steel_phys_mat,
                    "distance": 0.01,
                    "n_sub": 1,
                    "moment_modifier": moment_mod,
                    "element_type": TwoNodeLink,
                },
                "zerolength_gen_j": gravity_shear_tab,
                "zerolength_gen_args_j": {
                    "consider_composite": True,
                    "section": sec,
                    "n_parameter": n_parameter,
                    "physical_material": steel_phys_mat,
                    "distance": 0.01,
                    "n_sub": 1,
                    "moment_modifier": moment_mod,
                    "element_type": TwoNodeLink,
                },
            },
        )

    # leaning column
    mat = Elastic(
        uid=mdl.uid_generator.new("uniaxial material"),
        name="rigid_truss",
        e_mod=1.00e13,
    )
    outside_shape = rect_mesh(10.00, 10.00)  # for graphics

    for level_counter in range(num_levels):
        col_assembly = trg.add(
            x_grd["LC"],
            0.00,
            level_counter + 1,
            np.array((0.00, 0.00, 0.00)),
            "centroid",
            x_grd["LC"],
            0.00,
            level_counter,
            np.array((0.00, 0.00, 0.00)),
            "centroid",
            "Corotational",
            area=1.00,
            mat=mat,
            outside_shape=outside_shape,
            weight_per_length=0.00,
        )

        top_node = list(col_assembly.external_nodes.items())[0][1]
        top_node.restraint = [False, False, False, True, True, True]

        if no_diaphragm:
            # note required: taken care of by rigid diaphragm constraint.
            trg.add(
                x_grd["LC"],
                0.00,
                level_counter + 1,
                np.array((0.00, 0.00, 0.00)),
                "centroid",
                x_grd["G1"],
                0.00,
                level_counter + 1,
                np.array((0.00, 0.00, 0.00)),
                "centroid",
                "Linear",
                area=1.00,
                mat=mat,
                outside_shape=outside_shape,
                weight_per_length=0.00,
            )
            trg.add(
                x_grd["G2"],
                0.00,
                level_counter + 1,
                np.array((0.00, 0.00, 0.00)),
                "centroid",
                x_grd["1"],
                0.00,
                level_counter + 1,
                np.array((0.00, 0.00, 0.00)),
                "centroid",
                "Linear",
                area=1.00,
                mat=mat,
                outside_shape=outside_shape,
                weight_per_length=0.00,
            )

    # retrieve primary nodes (from the leaning column)
    p_nodes = []
    for i in range(num_levels + 1):
        p_nodes.append(query.search_node_lvl(x_grd["LC"], 0.00, i))

    # fix base
    for node in mdl.levels[0].nodes.values():
        node.restraint = [True] * 6

    loadcase = LoadCase("1.2D+0.25L+-E", mdl)
    self_weight(mdl, loadcase, factor=1.20)
    self_mass(mdl, loadcase)

    # apply beam udl
    xpt_tags = ("1", "2")

    for level_counter in range(1, num_levels + 1):
        level_tag = "level_" + str(level_counter)
        for xpt_tag in xpt_tags:
            xpt = x_grd[xpt_tag] + 12.00 * 12.00
            comp = query.retrieve_component(xpt, 0.00, level_counter)
            assert comp
            for elm in comp.elements.values():
                if isinstance(elm, ElasticBeamColumn):
                    loadcase.line_element_udl[elm.uid].add_glob(
                        np.array((0.00, 0.00, -beam_udls[level_tag]))
                    )

    # apply primary node load and mass
    for i, p_node in enumerate(p_nodes):
        if i == 0:
            continue
        level_tag = "level_" + str(i)
        loadcase.node_loads[p_node.uid].val += np.array(
            (0.00, 0.00, -lvl_weight[level_tag], 0.00, 0.00, 0.00)
        )
        mass = lvl_weight[level_tag] / G_CONST_IMPERIAL
        loadcase.node_mass[p_node.uid].val += np.array(
            (mass, 0.00, 0.00, 0.00, 0.00, 0.00)
        )

    if not no_diaphragm:
        # assign rigid diaphragm constraints
        loadcase.rigid_diaphragms(list(range(1, num_levels + 1)), gather_mass=True)

    return mdl, loadcase


def scbf_9_ii(direction) -> tuple[Model, LoadCase]:
    """
    9 story special concentrically braced frame risk category II
    archetype
    """

    if direction == "x":
        grav_bm_moment_mod = 5.50
        grav_col_moment_mod_interior = 1.00
        grav_col_moment_mod_exterior = 2.00
    elif direction == "y":
        grav_bm_moment_mod = 5.00
        grav_col_moment_mod_interior = 1.00
        grav_col_moment_mod_exterior = 2.00
    else:
        raise ValueError(f"Invalid direction: {direction}")

    level_elevs = (
        np.array(
            (
                15.00,
                13.00 + 15.00,
                13.00 * 2.00 + 15.00,
                13.00 * 3.00 + 15.00,
                13.00 * 4.00 + 15.00,
                13.00 * 5.00 + 15.00,
                13.00 * 6.00 + 15.00,
                13.00 * 7.00 + 15.00,
                13.00 * 8.00 + 15.00,
            )
        )
        * 12.00
    )

    sections = dict(
        gravity_cols=dict(
            level_1="W14X48",
            level_2="W14X48",
            level_3="W14X48",
            level_4="W14X48",
            level_5="W14X48",
            level_6="W14X48",
            level_7="W14X48",
            level_8="W14X48",
            level_9="W14X48",
        ),
        gravity_beams=dict(
            level_1="W16X31",
            level_2="W16X31",
            level_3="W16X31",
            level_4="W16X31",
            level_5="W16X31",
            level_6="W16X31",
            level_7="W16X31",
            level_8="W16X31",
            level_9="W16X31",
        ),
        lateral_cols=dict(
            level_1="W14X311",
            level_2="W14X311",
            level_3="W14X233",
            level_4="W14X233",
            level_5="W14X159",
            level_6="W14X159",
            level_7="W14X132",
            level_8="W14X132",
            level_9="W14X132",
        ),
        lateral_beams=dict(
            level_1="W18X106",
            level_2="W18X106",
            level_3="W18X97",
            level_4="W18X97",
            level_5="W18X97",
            level_6="W18X97",
            level_7="W18X86",
            level_8="W18X86",
            level_9="W18X35",
        ),
        braces=dict(
            level_1="HSS14.000X0.625",
            level_2="HSS12.750X0.500",
            level_3="HSS12.750X0.500",
            level_4="HSS12.750X0.500",
            level_5="HSS12.750X0.500",
            level_6="HSS10.000X0.625",
            level_7="HSS10.000X0.625",
            level_8="HSS8.625X0.625",
            level_9="HSS8.625X0.625",
        ),
    )

    metadata = dict(
        brace_buckling_length={
            1: 262.8945,
            2: 250.2764,
            3: 250.6551,
            4: 250.7603,
            5: 251.0654,
            6: 254.9689,
            7: 255.1230,
            8: 258.3746,
            9: 258.7150,
        },
        brace_l_c={
            1: 27.8341,
            2: 25.4090,
            3: 25.4090,
            4: 25.4090,
            5: 25.4090,
            6: 19.5407,
            7: 19.5407,
            8: 16.7005,
            9: 16.7005,
        },
        gusset_t_p={
            1: 1.1250,
            2: 1.0000,
            3: 1.0000,
            4: 1.0000,
            5: 1.0000,
            6: 1.1250,
            7: 1.1250,
            8: 1.1250,
            9: 1.1250,
        },
        gusset_avg_buckl_len={
            1: 20.4257,
            2: 18.9745,
            3: 19.0089,
            4: 19.0058,
            5: 19.0454,
            6: 20.4888,
            7: 20.4851,
            8: 20.3601,
            9: 20.2641,
        },
        hinge_dist={
            1: 47.9813,
            2: 47.9298,
            3: 47.6909,
            4: 47.6879,
            5: 47.5353,
            6: 46.0836,
            7: 45.9021,
            8: 44.3807,
            9: 43.8285,
        },
        plate_a={
            1: 111.0000,
            2: 101.0000,
            3: 101.0000,
            4: 101.0000,
            5: 101.0000,
            6: 78.0000,
            7: 78.0000,
            8: 66.0000,
            9: 66.0000,
        },
        plate_b={
            1: 66.6000,
            2: 52.5200,
            3: 52.5032,
            4: 52.5200,
            5: 52.5200,
            6: 40.5600,
            7: 40.5340,
            8: 34.3200,
            9: 34.2430,
        },
    )

    lvl_weight = dict(
        level_1=1027.266878 * 1e3 / 2.0,
        level_2=1020.737578 * 1e3 / 2.0,
        level_3=1020.963116 * 1e3 / 2.0,
        level_4=1020.838183 * 1e3 / 2.0,
        level_5=1021.489558 * 1e3 / 2.0,
        level_6=1025.176048 * 1e3 / 2.0,
        level_7=1024.136830 * 1e3 / 2.0,
        level_8=1025.580601 * 1e3 / 2.0,
        level_9=1130.669864 * 1e3 / 2.0,
    )  # lb (only the tributary weight for this frame)

    beam_udls = dict(
        level_1=74.0,
        level_2=74.0,
        level_3=74.0,
        level_4=74.0,
        level_5=74.0,
        level_6=74.0,
        level_7=74.0,
        level_8=74.0,
        level_9=74.0,
    )  # lb/in

    mdl, loadcase = generate_archetype(
        level_elevs,
        sections,
        metadata,
        "scbf_9_ii",
        grav_bm_moment_mod,
        grav_col_moment_mod_interior,
        grav_col_moment_mod_exterior,
        lvl_weight,
        beam_udls,
        no_diaphragm=False,
    )

    return mdl, loadcase
