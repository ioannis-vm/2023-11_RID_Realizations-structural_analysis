"""
Equivalent 2D models of the archetypes considered in this study.

"""

from copy import deepcopy
import numpy as np
import scipy as sp
import pandas as pd
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
from osmg.gen.steel.brb import BRBGenerator
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

    df_smf = pd.read_csv(
        "extra/structural_analysis/data/brbf_stiffness_modification_factors.csv",
        skiprows=6,
        index_col=(0),
    )
    df_smf = (
        df_smf.assign(
            WorkPtLen_ft=np.sqrt(df_smf.Bay_ft**2 + df_smf.Height_ft**2)
        )
        .drop(columns=["Bay_ft", "Height_ft"])
        .reset_index()
        .set_index(["Asc_in2", "WorkPtLen_ft"])
    )

    # cast to numpy arrays
    points_smf = np.array(df_smf.index.to_list()).tolist()
    values_smf = df_smf.to_numpy().reshape(-1)
    # generate interpolation function
    interp_smf = sp.interpolate.LinearNDInterpolator(points_smf, values_smf)

    df_acs = pd.read_csv(
        "extra/structural_analysis/data/brbf_approximate_casing_sizes.csv",
        skiprows=6,
        index_col=(0),
    )
    df_acs = (
        df_acs.assign(
            WorkPtLen_ft=np.sqrt(df_acs.Bay_ft**2 + df_acs.Height_ft**2)
        )
        .drop(columns=["Bay_ft", "Height_ft"])
        .reset_index()
        .set_index(["Asc_in2", "WorkPtLen_ft"])
    )

    # cast to numpy arrays
    points_acs = np.array(df_acs.index.to_list()).tolist()
    values_acs = np.array(
        [
            float(x.replace("t", "").replace("p", ""))
            for x in df_acs.to_numpy().reshape(-1)
        ]
    )
    # yes, we will draw everything as squares for our
    # visualization purposes..
    # generate interpolation function
    interp_acs = sp.interpolate.LinearNDInterpolator(points_acs, values_acs)

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
    hi_diff = np.diff(np.array((0.00, *level_elevs)))

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

    # system: smrf
    if lateral_system == "smrf":
        for level_counter in range(num_levels):
            level_tag = f"level_{level_counter+1}"
            mdl.levels.set_active([level_counter + 1])

            # add the lateral columns
            beam_depth = sec_collection.retrieve_by_attr(
                "name", sections["outer_frame"]["lateral_beams"][level_tag]
            ).properties["d"]

            for plcmt_tag in ("1", "2", "3", "4", "5"):
                if plcmt_tag == "1":
                    placement = "exterior"
                    pz_loc = "exterior_last"
                elif plcmt_tag == "5":
                    placement = "exterior"
                    pz_loc = "exterior_first"
                else:
                    placement = "interior"
                    pz_loc = "interior"
                sec = sec_collection.retrieve_by_attr(
                    "name",
                    sections["outer_frame"]["lateral_cols"][placement][level_tag],
                )
                sec_cp = deepcopy(sec)
                sec_cp.i_x *= (n_parameter + 1) / n_parameter
                sec_cp.i_y *= (n_parameter + 1) / n_parameter

                column_depth = sec.properties["d"]
                bcg.add_pz_active(
                    x_grd[plcmt_tag],
                    0.00,
                    sec,
                    steel_phys_mat,
                    np.pi / 2.00,
                    column_depth,
                    beam_depth,
                    "steel_w_col_pz_updated",
                    {
                        "pz_doubler_plate_thickness": (
                            metadata["outer_frame"][placement][level_tag]
                        ),
                        "axial_load_ratio": 0.00,
                        "slab_depth": 0.00,
                        "consider_composite": False,
                        "location": pz_loc,
                        "only_elastic": False,
                        "moment_modifier": 1.00,
                    },
                )
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

            # add the lateral beams
            sec = sec_collection.retrieve_by_attr(
                "name", sections["outer_frame"]["lateral_beams"][level_tag]
            )
            sec_cp = deepcopy(sec)
            sec_cp.i_x *= (n_parameter + 1) / n_parameter
            sec_cp.i_y *= (n_parameter + 1) / n_parameter

            for plcmt_i, plcmt_j in zip(("1", "2", "3", "4"), ("2", "3", "4", "5")):
                bcg.add_horizontal_active(
                    x_grd[plcmt_i],
                    0.00,
                    x_grd[plcmt_j],
                    0.00,
                    np.array((0.0, 0.0, 0.0)),
                    np.array((0.0, 0.0, 0.0)),
                    "middle_back",
                    "middle_front",
                    "Linear",
                    n_sub,
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
                            "section": sec,
                            "n_parameter": n_parameter,
                            "axial_load_ratio": 0.00,
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

            # add the inner frame (for RC IV smrf)
            if risk_category == "iv":
                # inner frame columns
                for plcmt_tag in ("6", "7", "8"):
                    if plcmt_tag in ("6", "8"):
                        placement = "exterior"
                    else:
                        placement = "interior"
                    sec = sec_collection.retrieve_by_attr(
                        "name",
                        sections["inner_frame"]["lateral_cols"][placement][
                            level_tag
                        ],
                    )
                    sec_cp = deepcopy(sec)
                    sec_cp.i_x *= (n_parameter + 1) / n_parameter
                    sec_cp.i_y *= (n_parameter + 1) / n_parameter
                    column_depth = sec.properties["d"]
                    bcg.add_pz_active(
                        x_grd[plcmt_tag],
                        0.00,
                        sec,
                        steel_phys_mat,
                        np.pi / 2.00,
                        column_depth,
                        beam_depth,
                        "steel_w_col_pz_updated",
                        {
                            "pz_doubler_plate_thickness": (
                                metadata["inner_frame"][placement][level_tag]
                            ),
                            "axial_load_ratio": 0.00,
                            "slab_depth": 0.00,
                            "consider_composite": False,
                            "location": "interior",
                            "only_elastic": False,
                            "moment_modifier": 1.00,
                        },
                    )
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

                # inner frame beams
                sec = sec_collection.retrieve_by_attr(
                    "name", sections["inner_frame"]["lateral_beams"][level_tag]
                )
                sec_cp = deepcopy(sec)
                sec_cp.i_x *= (n_parameter + 1) / n_parameter
                sec_cp.i_y *= (n_parameter + 1) / n_parameter
                for plcmt_i, plcmt_j in zip(("6", "7"), ("7", "8")):
                    bcg.add_horizontal_active(
                        x_grd[plcmt_i],
                        0.00,
                        x_grd[plcmt_j],
                        0.00,
                        np.array((0.0, 0.0, 0.0)),
                        np.array((0.0, 0.0, 0.0)),
                        "middle_back",
                        "middle_front",
                        "Linear",
                        n_sub,
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

    # system: scbf and brbf

    elif lateral_system in ("scbf", "brbf"):
        if lateral_system == "scbf":
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

                if lateral_system == "scbf":
                    brace_sec = mdl.fiber_sections.retrieve_by_attr(
                        "name", brace_sec_name
                    )

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

                elif lateral_system == "brbf":
                    brbg = BRBGenerator(mdl)
                    brace_sec_name = sections["braces"][level_tag]
                    area = float(brace_sec_name)
                    workpoint_length = np.sqrt(
                        (25.00 * 12.00) ** 2 + (hi_diff[level_counter]) ** 2
                    )  # in
                    trial_point = np.array((area, workpoint_length / 12.00))
                    stiffness_mod_factor = interp_smf(trial_point)[0]  # type: ignore
                    casing_size = interp_acs(trial_point)[0]  # type: ignore

                    brbg.add_brb(
                        x_i,
                        0.00,
                        level_counter + 1,
                        np.array((0.00, 0.00, vertical_offsets[level_counter])),
                        "bottom_node",
                        x_j,
                        0.00,
                        level_counter,
                        np.array((0.00, 0.00, vertical_offsets[level_counter])),
                        "top_node",
                        area,
                        38000.00 * 1.10,
                        29000 * 1e3 * stiffness_mod_factor,
                        casing_size,
                        150.00 / (12.00) ** 3,  # lb/in3, approximate brb weight
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
            if lateral_system == "smrf":
                sec = sec_collection.retrieve_by_attr(
                    "name",
                    sections["outer_frame"]["lateral_cols"][placement][level_tag],
                )
            else:
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
            if lateral_system == "smrf" and risk_category == "iv":
                trg.add(
                    x_grd["5"],
                    0.00,
                    level_counter + 1,
                    np.array((0.00, 0.00, 0.00)),
                    "centroid",
                    x_grd["6"],
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
    if lateral_system == "smrf":
        xpt_tags = ("1", "2", "3", "4")
    elif lateral_system in ["scbf", "brbf"]:
        xpt_tags = ("1", "2")
    else:
        raise ValueError(f"Invalid system: {lateral_system}")

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


def smrf_3_ii(direction) -> tuple[Model, LoadCase]:
    """
    3 story special moment frame risk category II archetype
    """

    if direction == "x":
        grav_bm_moment_mod = 6.00
        grav_col_moment_mod_interior = 3.00
        grav_col_moment_mod_exterior = 2.00
    elif direction == "y":
        grav_bm_moment_mod = 8.00
        grav_col_moment_mod_interior = 3.00
        grav_col_moment_mod_exterior = 2.00
    else:
        raise ValueError(f"Invalid direction: {direction}")

    level_elevs = np.array((15.00, 13.00 + 15.00, 13.00 + 13.00 + 15.00)) * 12.00

    sections = dict(
        gravity_cols=dict(level_1="W14X48", level_2="W14X48", level_3="W14X48"),
        gravity_beams=dict(level_1="W16X31", level_2="W16X31", level_3="W16X31"),
        outer_frame=dict(
            lateral_cols=dict(
                exterior=dict(level_1="W24X94", level_2="W24X94", level_3="W24X94"),
                interior=dict(
                    level_1="W24X176", level_2="W24X176", level_3="W24X176"
                ),
            ),
            lateral_beams=dict(
                level_1="W24X131", level_2="W24X84", level_3="W24X76"
            ),
        ),
    )

    doubler_plate_thicknesses = dict(
        outer_frame=dict(
            exterior=dict(level_1=0.8750, level_2=0.3125, level_3=0.2500),
            interior=dict(level_1=1.8125, level_2=0.7500, level_3=0.6250),
        )
    )

    lvl_weight = dict(
        level_1=1187.769325 * 1e3 / 2.0,
        level_2=1161.020256 * 1e3 / 2.0,
        level_3=1269.345010 * 1e3 / 2.0,
    )  # lb (only the tributary weight for this frame)

    beam_udls = dict(level_1=74.0, level_2=74.0, level_3=74.0)  # lb/in

    mdl, loadcase = generate_archetype(
        level_elevs,
        sections,
        doubler_plate_thicknesses,
        "smrf_3_ii",
        grav_bm_moment_mod,
        grav_col_moment_mod_interior,
        grav_col_moment_mod_exterior,
        lvl_weight,
        beam_udls,
        no_diaphragm=False,
    )

    return mdl, loadcase


def smrf_3_iv(direction) -> tuple[Model, LoadCase]:
    """
    3 story special moment frame risk category IV archetype
    """

    if direction == "x":
        grav_bm_moment_mod = 2.00
        grav_col_moment_mod_interior = 4.00
        grav_col_moment_mod_exterior = 4.00
    elif direction == "y":
        grav_bm_moment_mod = 2.00
        grav_col_moment_mod_interior = 4.00
        grav_col_moment_mod_exterior = 4.00
    else:
        raise ValueError(f"Invalid direction: {direction}")

    level_elevs = np.array((15.00, 13.00 + 15.00, 13.00 + 13.00 + 15.00)) * 12.00

    sections = dict(
        gravity_cols=dict(level_1="W14X48", level_2="W14X48", level_3="W14X48"),
        gravity_beams=dict(level_1="W16X31", level_2="W16X31", level_3="W16X31"),
        outer_frame=dict(
            lateral_cols=dict(
                exterior=dict(
                    level_1="W24X146", level_2="W24X146", level_3="W24X146"
                ),
                interior=dict(
                    level_1="W24X279", level_2="W24X279", level_3="W24X279"
                ),
            ),
            lateral_beams=dict(
                level_1="W33X169", level_2="W33X169", level_3="W24X76"
            ),
        ),
        inner_frame=dict(
            lateral_cols=dict(
                exterior=dict(level_1="W21X62", level_2="W21X62", level_3="W21X62"),
                interior=dict(
                    level_1="W24X103", level_2="W24X103", level_3="W24X94"
                ),
            ),
            lateral_beams=dict(level_1="W24X76", level_2="W24X76", level_3="W24X76"),
        ),
    )

    doubler_plate_thicknesses = dict(
        outer_frame=dict(
            exterior=dict(level_1=1.00, level_2=1.00, level_3=0.25),
            interior=dict(level_1=1.75, level_2=1.75, level_3=0.00),
        ),
        inner_frame=dict(
            exterior=dict(level_1=0.5000, level_2=0.5000, level_3=0.5000),
            interior=dict(level_1=0.9375, level_2=0.9375, level_3=1.0000),
        ),
    )

    lvl_weight = dict(
        level_1=1201.500296 * 1e3 / 2.0,
        level_2=1183.251104 * 1e3 / 2.0,
        level_3=1279.011813 * 1e3 / 2.0,
    )  # lb (only the tributary weight for this frame)

    beam_udls = dict(level_1=74.0, level_2=74.0, level_3=74.0)  # lb/in

    mdl, loadcase = generate_archetype(
        level_elevs,
        sections,
        doubler_plate_thicknesses,
        "smrf_3_iv",
        grav_bm_moment_mod,
        grav_col_moment_mod_interior,
        grav_col_moment_mod_exterior,
        lvl_weight,
        beam_udls,
        no_diaphragm=False,
    )

    return mdl, loadcase


def smrf_6_ii(direction) -> tuple[Model, LoadCase]:
    """
    6 story special moment frame risk category II archetype
    """

    if direction == "x":
        grav_bm_moment_mod = 6.00
        grav_col_moment_mod_interior = 3.00
        grav_col_moment_mod_exterior = 2.00
    elif direction == "y":
        grav_bm_moment_mod = 8.00
        grav_col_moment_mod_interior = 3.00
        grav_col_moment_mod_exterior = 2.00
    else:
        raise ValueError(f"Invalid direction: {direction}")

    level_elevs = (
        np.array(
            (
                15.00,
                1.00 * 13.00 + 15.00,
                2.00 * 13.00 + 15.00,
                3.00 * 13.00 + 15.00,
                4.00 * 13.00 + 15.00,
                5.00 * 13.00 + 15.00,
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
        ),
        gravity_beams=dict(
            level_1="W16X31",
            level_2="W16X31",
            level_3="W16X31",
            level_4="W16X31",
            level_5="W16X31",
            level_6="W16X31",
        ),
        outer_frame=dict(
            lateral_cols=dict(
                exterior=dict(
                    level_1="W27X114",
                    level_2="W27X114",
                    level_3="W27X102",
                    level_4="W27X102",
                    level_5="W27X94",
                    level_6="W27X94",
                ),
                interior=dict(
                    level_1="W27X217",
                    level_2="W27X217",
                    level_3="W27X161",
                    level_4="W27X161",
                    level_5="W27X129",
                    level_6="W27X129",
                ),
            ),
            lateral_beams=dict(
                level_1="W33X130",
                level_2="W33X130",
                level_3="W30X108",
                level_4="W30X108",
                level_5="W27X94",
                level_6="W27X94",
            ),
        ),
    )

    doubler_plate_thicknesses = dict(
        outer_frame=dict(
            exterior=dict(
                level_1=0.5625,
                level_2=0.5625,
                level_3=0.4375,
                level_4=0.4375,
                level_5=0.3750,
                level_6=0.3750,
            ),
            interior=dict(
                level_1=1.250,
                level_2=1.250,
                level_3=1.125,
                level_4=1.125,
                level_5=1.000,
                level_6=1.000,
            ),
        )
    )

    lvl_weight = dict(
        level_1=1087.289497 * 1e3 / 2.0,
        level_2=1075.759778 * 1e3 / 2.0,
        level_3=1068.798496 * 1e3 / 2.0,
        level_4=1065.981046 * 1e3 / 2.0,
        level_5=1061.929727 * 1e3 / 2.0,
        level_6=1211.687073 * 1e3 / 2.0,
    )  # lb (only the tributary weight for this frame)

    beam_udls = dict(
        level_1=74.0,
        level_2=74.0,
        level_3=74.0,
        level_4=74.0,
        level_5=74.0,
        level_6=74.0,
    )  # lb/in

    mdl, loadcase = generate_archetype(
        level_elevs,
        sections,
        doubler_plate_thicknesses,
        "smrf_6_ii",
        grav_bm_moment_mod,
        grav_col_moment_mod_interior,
        grav_col_moment_mod_exterior,
        lvl_weight,
        beam_udls,
        no_diaphragm=False,
    )

    return mdl, loadcase


def smrf_6_iv(direction) -> tuple[Model, LoadCase]:
    """
    6 story special moment frame risk category IV archetype
    """

    if direction == "x":
        grav_bm_moment_mod = 2.00
        grav_col_moment_mod_interior = 4.00
        grav_col_moment_mod_exterior = 4.00
    elif direction == "y":
        grav_bm_moment_mod = 2.00
        grav_col_moment_mod_interior = 4.00
        grav_col_moment_mod_exterior = 4.00
    else:
        raise ValueError(f"Invalid direction: {direction}")

    level_elevs = (
        np.array(
            (
                15.00,
                1.00 * 13.00 + 15.00,
                2.00 * 13.00 + 15.00,
                3.00 * 13.00 + 15.00,
                4.00 * 13.00 + 15.00,
                5.00 * 13.00 + 15.00,
            )
        )
        * 12.00
    )

    sections = dict(
        gravity_cols=dict(
            level_1="W14X61",
            level_2="W14X61",
            level_3="W14X61",
            level_4="W14X48",
            level_5="W14X48",
            level_6="W14X48",
        ),
        gravity_beams=dict(
            level_1="W16X31",
            level_2="W16X31",
            level_3="W16X31",
            level_4="W16X31",
            level_5="W16X31",
            level_6="W16X31",
        ),
        outer_frame=dict(
            lateral_cols=dict(
                exterior=dict(
                    level_1="W24X192",
                    level_2="W24X176",
                    level_3="W24X176",
                    level_4="W24X146",
                    level_5="W24X146",
                    level_6="W24X146",
                ),
                interior=dict(
                    level_1="W24X370",
                    level_2="W24X370",
                    level_3="W24X279",
                    level_4="W24X279",
                    level_5="W24X250",
                    level_6="W24X250",
                ),
            ),
            lateral_beams=dict(
                level_1="W36X182",
                level_2="W36X182",
                level_3="W36X170",
                level_4="W36X160",
                level_5="W33X130",
                level_6="W24X76",
            ),
        ),
        inner_frame=dict(
            lateral_cols=dict(
                exterior=dict(
                    level_1="W24X162",
                    level_2="W24X162",
                    level_3="W24X146",
                    level_4="W24X84",
                    level_5="W24X76",
                    level_6="W24X76",
                ),
                interior=dict(
                    level_1="W24X306",
                    level_2="W24X306",
                    level_3="W24X250",
                    level_4="W24X192",
                    level_5="W24X103",
                    level_6="W24X103",
                ),
            ),
            lateral_beams=dict(
                level_1="W27X194",
                level_2="W27X194",
                level_3="W27X146",
                level_4="W27X94",
                level_5="W24X76",
                level_6="W24X76",
            ),
        ),
    )

    doubler_plate_thicknesses = dict(
        outer_frame=dict(
            exterior=dict(
                level_1=0.8125,
                level_2=0.9375,
                level_3=0.8125,
                level_4=0.8750,
                level_5=0.5625,
                level_6=0.2500,
            ),
            interior=dict(
                level_1=1.3125,
                level_2=1.3125,
                level_3=1.6875,
                level_4=1.5000,
                level_5=1.1250,
                level_6=0.2500,
            ),
        ),
        inner_frame=dict(
            exterior=dict(
                level_1=1.2500,
                level_2=1.2500,
                level_3=0.8125,
                level_4=0.4375,
                level_5=0.3125,
                level_6=0.3125,
            ),
            interior=dict(
                level_1=2.1875,
                level_2=2.1875,
                level_3=1.6250,
                level_4=0.8750,
                level_5=0.9375,
                level_6=0.9375,
            ),
        ),
    )

    lvl_weight = dict(
        level_1=1132.949635 * 1e3 / 2.0,
        level_2=1117.975472 * 1e3 / 2.0,
        level_3=1103.119207 * 1e3 / 2.0,
        level_4=1089.099875 * 1e3 / 2.0,
        level_5=1077.206119 * 1e3 / 2.0,
        level_6=1178.443330 * 1e3 / 2.0,
    )  # lb (only the tributary weight for this frame)

    beam_udls = dict(
        level_1=74.0,
        level_2=74.0,
        level_3=74.0,
        level_4=74.0,
        level_5=74.0,
        level_6=74.0,
    )  # lb/in

    mdl, loadcase = generate_archetype(
        level_elevs,
        sections,
        doubler_plate_thicknesses,
        "smrf_6_iv",
        grav_bm_moment_mod,
        grav_col_moment_mod_interior,
        grav_col_moment_mod_exterior,
        lvl_weight,
        beam_udls,
        no_diaphragm=False,
    )

    return mdl, loadcase


def smrf_9_ii(direction) -> tuple[Model, LoadCase]:
    """
    9 story special moment frame risk category II archetype
    """

    if direction == "x":
        grav_bm_moment_mod = 6.00
        grav_col_moment_mod_interior = 3.00
        grav_col_moment_mod_exterior = 2.00
    elif direction == "y":
        grav_bm_moment_mod = 8.00
        grav_col_moment_mod_interior = 3.00
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
            level_1="W14X82",
            level_2="W14X82",
            level_3="W14X82",
            level_4="W14X61",
            level_5="W14X61",
            level_6="W14X61",
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
        outer_frame=dict(
            lateral_cols=dict(
                exterior=dict(
                    level_1="W27X194",
                    level_2="W27X194",
                    level_3="W27X146",
                    level_4="W27X146",
                    level_5="W27X102",
                    level_6="W27X102",
                    level_7="W27X94",
                    level_8="W27X94",
                    level_9="W27X94",
                ),
                interior=dict(
                    level_1="W27X307",
                    level_2="W27X307",
                    level_3="W27X235",
                    level_4="W27X235",
                    level_5="W27X194",
                    level_6="W27X161",
                    level_7="W27X161",
                    level_8="W27X129",
                    level_9="W27X129",
                ),
            ),
            lateral_beams=dict(
                level_1="W33X141",
                level_2="W33X141",
                level_3="W33X130",
                level_4="W33X130",
                level_5="W30X116",
                level_6="W30X116",
                level_7="W27X94",
                level_8="W27X94",
                level_9="W27X94",
            ),
        ),
    )

    doubler_plate_thicknesses = dict(
        outer_frame=dict(
            exterior=dict(
                level_1=0.5000,
                level_2=0.5000,
                level_3=0.5625,
                level_4=0.5625,
                level_5=0.5000,
                level_6=0.5625,
                level_7=0.3750,
                level_8=0.3750,
                level_9=0.3750,
            ),
            interior=dict(
                level_1=1.2500,
                level_2=1.3750,
                level_3=1.3750,
                level_4=1.3750,
                level_5=1.1250,
                level_6=1.3125,
                level_7=0.9375,
                level_8=1.0000,
                level_9=1.0000,
            ),
        )
    )

    lvl_weight = dict(
        level_1=1067.797366 * 1e3 / 2.0,
        level_2=1056.619265 * 1e3 / 2.0,
        level_3=1049.165622 * 1e3 / 2.0,
        level_4=1044.488377 * 1e3 / 2.0,
        level_5=1038.849956 * 1e3 / 2.0,
        level_6=1037.052685 * 1e3 / 2.0,
        level_7=1030.029166 * 1e3 / 2.0,
        level_8=1028.271077 * 1e3 / 2.0,
        level_9=1138.171239 * 1e3 / 2.0,
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
        doubler_plate_thicknesses,
        "smrf_9_ii",
        grav_bm_moment_mod,
        grav_col_moment_mod_interior,
        grav_col_moment_mod_exterior,
        lvl_weight,
        beam_udls,
        no_diaphragm=False,
    )

    return mdl, loadcase


def smrf_9_iv(direction) -> tuple[Model, LoadCase]:
    """
    9 story special moment frame risk category IV archetype
    """

    if direction == "x":
        grav_bm_moment_mod = 2.00
        grav_col_moment_mod_interior = 4.00
        grav_col_moment_mod_exterior = 4.00
    elif direction == "y":
        grav_bm_moment_mod = 2.00
        grav_col_moment_mod_interior = 4.00
        grav_col_moment_mod_exterior = 4.00
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
            level_1="W14X82",
            level_2="W14X82",
            level_3="W14X82",
            level_4="W14X61",
            level_5="W14X61",
            level_6="W14X61",
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
        outer_frame=dict(
            lateral_cols=dict(
                exterior=dict(
                    level_1="W27X258",
                    level_2="W27X258",
                    level_3="W27X235",
                    level_4="W27X235",
                    level_5="W27X194",
                    level_6="W27X194",
                    level_7="W27X161",
                    level_8="W27X161",
                    level_9="W27X114",
                ),
                interior=dict(
                    level_1="W27X539",
                    level_2="W27X539",
                    level_3="W27X539",
                    level_4="W27X539",
                    level_5="W27X539",
                    level_6="W27X307",
                    level_7="W27X307",
                    level_8="W27X217",
                    level_9="W27X217",
                ),
            ),
            lateral_beams=dict(
                level_1="W36X256",
                level_2="W36X256",
                level_3="W36X256",
                level_4="W36X256",
                level_5="W36X232",
                level_6="W36X194",
                level_7="W36X160",
                level_8="W33X141",
                level_9="W27X94",
            ),
        ),
        inner_frame=dict(
            lateral_cols=dict(
                exterior=dict(
                    level_1="W27X217",
                    level_2="W27X217",
                    level_3="W27X217",
                    level_4="W27X217",
                    level_5="W27X146",
                    level_6="W27X129",
                    level_7="W27X129",
                    level_8="W27X94",
                    level_9="W27X94",
                ),
                interior=dict(
                    level_1="W27X539",
                    level_2="W27X539",
                    level_3="W27X368",
                    level_4="W27X368",
                    level_5="W27X258",
                    level_6="W27X258",
                    level_7="W27X194",
                    level_8="W27X194",
                    level_9="W27X194",
                ),
            ),
            lateral_beams=dict(
                level_1="W27X281",
                level_2="W27X281",
                level_3="W27X281",
                level_4="W27X235",
                level_5="W27X194",
                level_6="W27X178",
                level_7="W27X129",
                level_8="W27X102",
                level_9="W27X94",
            ),
        ),
    )

    doubler_plate_thicknesses = dict(
        outer_frame=dict(
            exterior=dict(
                level_1=1.0625,
                level_2=1.0625,
                level_3=1.1875,
                level_4=1.1875,
                level_5=1.1875,
                level_6=0.8125,
                level_7=0.6875,
                level_8=0.5625,
                level_9=0.2500,
            ),
            interior=dict(
                level_1=1.3750,
                level_2=1.3750,
                level_3=1.3750,
                level_4=1.3750,
                level_5=1.0000,
                level_6=1.8125,
                level_7=1.2500,
                level_8=1.4375,
                level_9=0.6250,
            ),
        ),
        inner_frame=dict(
            exterior=dict(
                level_1=1.6250,
                level_2=1.6250,
                level_3=1.6250,
                level_4=1.1875,
                level_5=1.1875,
                level_6=1.0000,
                level_7=0.5000,
                level_8=0.4375,
                level_9=0.3750,
            ),
            interior=dict(
                level_1=1.8750,
                level_2=1.8750,
                level_3=3.0625,
                level_4=2.3125,
                level_5=2.3125,
                level_6=2.0000,
                level_7=1.4375,
                level_8=0.9375,
                level_9=0.7500,
            ),
        ),
    )

    lvl_weight = dict(
        level_1=1146.277592 * 1e3 / 2.0,
        level_2=1129.530625 * 1e3 / 2.0,
        level_3=1124.968239 * 1e3 / 2.0,
        level_4=1119.261563 * 1e3 / 2.0,
        level_5=1101.884645 * 1e3 / 2.0,
        level_6=1079.186909 * 1e3 / 2.0,
        level_7=1063.862381 * 1e3 / 2.0,
        level_8=1050.753697 * 1e3 / 2.0,
        level_9=1150.115474 * 1e3 / 2.0,
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
        doubler_plate_thicknesses,
        "smrf_9_iv",
        grav_bm_moment_mod,
        grav_col_moment_mod_interior,
        grav_col_moment_mod_exterior,
        lvl_weight,
        beam_udls,
        no_diaphragm=False,
    )

    return mdl, loadcase


def scbf_3_ii(direction) -> tuple[Model, LoadCase]:
    """
    3 story special concentrically braced frame risk category II
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

    level_elevs = np.array((15.00, 13.00 + 15.00, 13.00 + 13.00 + 15.00)) * 12.00

    sections = dict(
        gravity_cols=dict(level_1="W14X48", level_2="W14X48", level_3="W14X48"),
        gravity_beams=dict(level_1="W16X31", level_2="W16X31", level_3="W16X31"),
        lateral_cols=dict(level_1="W14X132", level_2="W14X132", level_3="W14X132"),
        lateral_beams=dict(level_1="W18X86", level_2="W18X86", level_3="W18X86"),
        braces=dict(
            level_1="HSS9.625X0.500",
            level_2="HSS8.625X0.625",
            level_3="HSS8.625X0.625",
        ),
    )

    metadata = dict(
        brace_buckling_length={1: 277.1226, 2: 258.3746, 3: 258.3746},
        brace_l_c={1: 19.0213, 2: 16.7005, 3: 16.7005},
        gusset_t_p={1: 1.0000, 2: 1.1250, 3: 1.1250},
        gusset_avg_buckl_len={1: 17.3715, 2: 20.3601, 3: 20.3601},
        hinge_dist={1: 40.3673, 2: 44.3807, 3: 44.3807},
        plate_a={1: 76.0000, 2: 66.0000, 3: 66.0000},
        plate_b={1: 45.6000, 2: 34.3200, 3: 34.3200},
    )

    lvl_weight = dict(
        level_1=1168.970755 * 1e3 / 2.0,
        level_2=1157.592778 * 1e3 / 2.0,
        level_3=1266.498683 * 1e3 / 2.0,
    )  # lb (only the tributary weight for this frame)

    beam_udls = dict(level_1=74.0, level_2=74.0, level_3=74.0)  # lb/in

    mdl, loadcase = generate_archetype(
        level_elevs,
        sections,
        metadata,
        "scbf_3_ii",
        grav_bm_moment_mod,
        grav_col_moment_mod_interior,
        grav_col_moment_mod_exterior,
        lvl_weight,
        beam_udls,
        no_diaphragm=False,
    )

    return mdl, loadcase


def scbf_3_iv(direction) -> tuple[Model, LoadCase]:
    """
    3 story special concentrically braced frame risk category IV
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

    level_elevs = np.array((15.00, 13.00 + 15.00, 13.00 + 13.00 + 15.00)) * 12.00

    sections = dict(
        gravity_cols=dict(level_1="W14X48", level_2="W14X48", level_3="W14X48"),
        gravity_beams=dict(level_1="W16X31", level_2="W16X31", level_3="W16X31"),
        lateral_cols=dict(level_1="W14X132", level_2="W14X132", level_3="W14X132"),
        lateral_beams=dict(level_1="W18X86", level_2="W18X60", level_3="W18X35"),
        braces=dict(
            level_1="HSS8.625X0.625",
            level_2="HSS8.625X0.625",
            level_3="HSS7.625X0.375",
        ),
    )

    metadata = dict(
        brace_buckling_length={1: 277.0718, 2: 258.4769, 3: 268.1875},
        brace_l_c={1: 16.7005, 2: 16.7005, 3: 15.0926},
        gusset_t_p={1: 1.1250, 2: 1.1250, 3: 0.8125},
        gusset_avg_buckl_len={1: 18.9243, 2: 20.3322, 3: 15.1637},
        hinge_dist={1: 40.8927, 2: 44.2227, 3: 37.9504},
        plate_a={1: 66.0000, 2: 66.0000, 3: 60.0000},
        plate_b={1: 39.6000, 2: 34.2980, 3: 31.1500},
    )

    lvl_weight = dict(
        level_1=1164.308019 * 1e3 / 4.0,
        level_2=1146.003591 * 1e3 / 4.0,
        level_3=1252.341283 * 1e3 / 4.0,
    )  # lb (only the tributary weight for this frame)

    beam_udls = dict(level_1=74.0, level_2=74.0, level_3=74.0)  # lb/in

    mdl, loadcase = generate_archetype(
        level_elevs,
        sections,
        metadata,
        "scbf_3_iv",
        grav_bm_moment_mod,
        grav_col_moment_mod_interior,
        grav_col_moment_mod_exterior,
        lvl_weight,
        beam_udls,
        no_diaphragm=False,
    )

    return mdl, loadcase


def scbf_6_ii(direction) -> tuple[Model, LoadCase]:
    """
    6 story special concentrically braced frame risk category II
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
        ),
        gravity_beams=dict(
            level_1="W16X31",
            level_2="W16X31",
            level_3="W16X31",
            level_4="W16X31",
            level_5="W16X31",
            level_6="W16X31",
        ),
        lateral_cols=dict(
            level_1="W14X211",
            level_2="W14X211",
            level_3="W14X132",
            level_4="W14X132",
            level_5="W14X74",
            level_6="W14X74",
        ),
        lateral_beams=dict(
            level_1="W18X97",
            level_2="W18X97",
            level_3="W18X97",
            level_4="W18X86",
            level_5="W18X86",
            level_6="W18X35",
        ),
        braces=dict(
            level_1="HSS12.750X0.500",
            level_2="HSS10.000X0.625",
            level_3="HSS10.000X0.625",
            level_4="HSS10.000X0.625",
            level_5="HSS8.625X0.625",
            level_6="HSS8.625X0.625",
        ),
    )

    metadata = dict(
        brace_buckling_length={
            1: 268.9417,
            2: 254.8040,
            3: 255.0238,
            4: 255.1230,
            5: 258.4881,
            6: 258.8131,
        },
        brace_l_c={
            1: 25.4090,
            2: 19.5407,
            3: 19.5407,
            4: 19.5407,
            5: 16.7005,
            6: 16.7005,
        },
        gusset_t_p={
            1: 1.0000,
            2: 1.1250,
            3: 1.1250,
            4: 1.1250,
            5: 1.1250,
            6: 1.1250,
        },
        gusset_avg_buckl_len={
            1: 18.3244,
            2: 20.4391,
            3: 20.5072,
            4: 20.4851,
            5: 20.4081,
            6: 20.3100,
        },
        hinge_dist={
            1: 44.4577,
            2: 46.1660,
            3: 46.0561,
            4: 45.9021,
            5: 44.3240,
            6: 43.7703,
        },
        plate_a={
            1: 101.0000,
            2: 78.0000,
            3: 78.0000,
            4: 78.0000,
            5: 66.0000,
            6: 66.0000,
        },
        plate_b={
            1: 60.6000,
            2: 40.5600,
            3: 40.5600,
            4: 40.5340,
            5: 34.3200,
            6: 34.2430,
        },
    )

    lvl_weight = dict(
        level_1=1061.493934 * 1e3 / 2.0,
        level_2=1057.530304 * 1e3 / 2.0,
        level_3=1057.435037 * 1e3 / 2.0,
        level_4=1056.880705 * 1e3 / 2.0,
        level_5=1058.123863 * 1e3 / 2.0,
        level_6=1163.961360 * 1e3 / 2.0,
    )  # lb (only the tributary weight for this frame)

    beam_udls = dict(
        level_1=74.0,
        level_2=74.0,
        level_3=74.0,
        level_4=74.0,
        level_5=74.0,
        level_6=74.0,
    )  # lb/in

    mdl, loadcase = generate_archetype(
        level_elevs,
        sections,
        metadata,
        "scbf_6_ii",
        grav_bm_moment_mod,
        grav_col_moment_mod_interior,
        grav_col_moment_mod_exterior,
        lvl_weight,
        beam_udls,
        no_diaphragm=False,
    )

    return mdl, loadcase


def scbf_6_iv(direction) -> tuple[Model, LoadCase]:
    """
    6 story special concentrically braced frame risk category IV
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
        ),
        gravity_beams=dict(
            level_1="W16X31",
            level_2="W16X31",
            level_3="W16X31",
            level_4="W16X31",
            level_5="W16X31",
            level_6="W16X31",
        ),
        lateral_cols=dict(
            level_1="W14X193",
            level_2="W14X193",
            level_3="W14X132",
            level_4="W14X132",
            level_5="W14X68",
            level_6="W14X68",
        ),
        lateral_beams=dict(
            level_1="W18X86",
            level_2="W18X86",
            level_3="W18X86",
            level_4="W18X86",
            level_5="W18X60",
            level_6="W18X35",
        ),
        braces=dict(
            level_1="HSS10.000X0.625",
            level_2="HSS10.000X0.625",
            level_3="HSS8.625X0.625",
            level_4="HSS8.625X0.625",
            level_5="HSS8.625X0.625",
            level_6="HSS7.625X0.375",
        ),
    )

    metadata = dict(
        brace_buckling_length={
            1: 273.6893,
            2: 255.1650,
            3: 258.3746,
            4: 258.3746,
            5: 258.6226,
            6: 268.3380,
        },
        brace_l_c={
            1: 19.5407,
            2: 19.5407,
            3: 16.7005,
            4: 16.7005,
            5: 16.7005,
            6: 15.0926,
        },
        gusset_t_p={
            1: 1.1250,
            2: 1.1250,
            3: 1.1250,
            4: 1.1250,
            5: 1.1250,
            6: 0.8125,
        },
        gusset_avg_buckl_len={
            1: 19.1980,
            2: 20.4200,
            3: 20.3601,
            4: 20.3601,
            5: 20.3951,
            6: 15.2223,
        },
        hinge_dist={
            1: 42.5839,
            2: 45.9856,
            3: 44.3807,
            4: 44.3807,
            5: 44.1495,
            6: 37.8742,
        },
        plate_a={
            1: 78.0000,
            2: 78.0000,
            3: 66.0000,
            4: 66.0000,
            5: 66.0000,
            6: 60.0000,
        },
        plate_b={
            1: 46.8000,
            2: 40.5600,
            3: 34.3200,
            4: 34.3200,
            5: 34.2980,
            6: 31.1500,
        },
    )

    lvl_weight = dict(
        level_1=1060.494158 * 1e3 / 4.0,
        level_2=1051.656858 * 1e3 / 4.0,
        level_3=1054.551007 * 1e3 / 4.0,
        level_4=1052.916546 * 1e3 / 4.0,
        level_5=1047.471230 * 1e3 / 4.0,
        level_6=1152.879689 * 1e3 / 4.0,
    )  # lb (only the tributary weight for this frame)

    beam_udls = dict(
        level_1=74.0,
        level_2=74.0,
        level_3=74.0,
        level_4=74.0,
        level_5=74.0,
        level_6=74.0,
    )  # lb/in

    mdl, loadcase = generate_archetype(
        level_elevs,
        sections,
        metadata,
        "scbf_6_iv",
        grav_bm_moment_mod,
        grav_col_moment_mod_interior,
        grav_col_moment_mod_exterior,
        lvl_weight,
        beam_udls,
        no_diaphragm=False,
    )

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


def scbf_9_iv(direction) -> tuple[Model, LoadCase]:
    """
    9 story special concentrically braced frame risk category IV
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
            level_3="W14X257",
            level_4="W14X257",
            level_5="W14X176",
            level_6="W14X176",
            level_7="W14X132",
            level_8="W14X132",
            level_9="W14X132",
        ),
        lateral_beams=dict(
            level_1="W18X130",
            level_2="W18X130",
            level_3="W18X106",
            level_4="W18X106",
            level_5="W18X97",
            level_6="W18X97",
            level_7="W18X86",
            level_8="W18X86",
            level_9="W18X35",
        ),
        braces=dict(
            level_1="HSS14.000X0.625",
            level_2="HSS14.000X0.625",
            level_3="HSS12.750X0.500",
            level_4="HSS12.750X0.500",
            level_5="HSS12.750X0.500",
            level_6="HSS10.750X0.500",
            level_7="HSS10.000X0.625",
            level_8="HSS9.625X0.500",
            level_9="HSS8.625X0.625",
        ),
    )

    metadata = dict(
        brace_buckling_length={
            1: 262.1255,
            2: 243.6128,
            3: 249.7887,
            4: 250.4779,
            5: 250.9142,
            6: 255.8393,
            7: 255.1230,
            8: 258.9488,
            9: 258.7150,
        },
        brace_l_c={
            1: 27.8341,
            2: 27.8341,
            3: 25.4090,
            4: 25.4090,
            5: 25.4090,
            6: 21.2925,
            7: 19.5407,
            8: 19.0213,
            9: 16.7005,
        },
        gusset_t_p={
            1: 1.1250,
            2: 1.1250,
            3: 1.0000,
            4: 1.0000,
            5: 1.0000,
            6: 1.0000,
            7: 1.1250,
            8: 1.0000,
            9: 1.1250,
        },
        gusset_avg_buckl_len={
            1: 20.4390,
            2: 21.1966,
            3: 19.0106,
            4: 18.9977,
            5: 19.0427,
            6: 18.6312,
            7: 20.4851,
            8: 18.4479,
            9: 20.2641,
        },
        hinge_dist={
            1: 48.3658,
            2: 51.7616,
            3: 47.8665,
            4: 47.8291,
            5: 47.5613,
            6: 45.1484,
            7: 45.9021,
            8: 43.5936,
            9: 43.8285,
        },
        plate_a={
            1: 111.0000,
            2: 111.0000,
            3: 101.0000,
            4: 101.0000,
            5: 101.0000,
            6: 85.0000,
            7: 78.0000,
            8: 76.0000,
            9: 66.0000,
        },
        plate_b={
            1: 66.6000,
            2: 57.7200,
            3: 52.4190,
            4: 52.5200,
            5: 52.5032,
            6: 44.2000,
            7: 40.5340,
            8: 39.5200,
            9: 34.2430,
        },
    )

    lvl_weight = dict(
        level_1=1030.042386 * 1e3 / 4.0,
        level_2=1022.172254 * 1e3 / 4.0,
        level_3=1021.692614 * 1e3 / 4.0,
        level_4=1017.577814 * 1e3 / 4.0,
        level_5=1017.923971 * 1e3 / 4.0,
        level_6=1021.498511 * 1e3 / 4.0,
        level_7=1020.713547 * 1e3 / 4.0,
        level_8=1019.779789 * 1e3 / 4.0,
        level_9=1123.520748 * 1e3 / 4.0,
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
        "scbf_9_iv",
        grav_bm_moment_mod,
        grav_col_moment_mod_interior,
        grav_col_moment_mod_exterior,
        lvl_weight,
        beam_udls,
        no_diaphragm=False,
    )

    return mdl, loadcase


def brbf_3_ii(direction) -> tuple[Model, LoadCase]:
    """
    3 story special buckling restrained braced frame risk category II
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

    level_elevs = np.array((15.00, 13.00 + 15.00, 13.00 + 13.00 + 15.00)) * 12.00

    sections = dict(
        gravity_cols=dict(level_1="W14X48", level_2="W14X48", level_3="W14X48"),
        gravity_beams=dict(level_1="W16X31", level_2="W16X31", level_3="W16X31"),
        lateral_cols=dict(level_1="W14X68", level_2="W14X68", level_3="W14X53"),
        lateral_beams=dict(level_1="W18X86", level_2="W18X86", level_3="W18X35"),
        braces=dict(level_1="7.00", level_2="5.50", level_3="4.00"),
    )

    metadata = dict(
        plate_a={1: 40.0000, 2: 40.0000, 3: 40.0000},
        plate_b={1: 20.0000, 2: 20.0000, 3: 20.0000},
    )

    lvl_weight = dict(
        level_1=1180.508957 * 1e3 / 2.0,
        level_2=1165.462570 * 1e3 / 2.0,
        level_3=1268.918283 * 1e3 / 2.0,
    )  # lb (only the tributary weight for this frame)

    beam_udls = dict(level_1=74.0, level_2=74.0, level_3=74.0)  # lb/in

    mdl, loadcase = generate_archetype(
        level_elevs,
        sections,
        metadata,
        "brbf_3_ii",
        grav_bm_moment_mod,
        grav_col_moment_mod_interior,
        grav_col_moment_mod_exterior,
        lvl_weight,
        beam_udls,
        no_diaphragm=False,
    )

    return mdl, loadcase


def brbf_3_iv(direction) -> tuple[Model, LoadCase]:
    """
    3 story special buckling restrained braced frame risk category IV
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

    level_elevs = np.array((15.00, 13.00 + 15.00, 13.00 + 13.00 + 15.00)) * 12.00

    sections = dict(
        gravity_cols=dict(level_1="W14X48", level_2="W14X48", level_3="W14X48"),
        gravity_beams=dict(level_1="W16X31", level_2="W16X31", level_3="W16X31"),
        lateral_cols=dict(level_1="W14X48", level_2="W14X48", level_3="W14X48"),
        lateral_beams=dict(level_1="W18X86", level_2="W18X86", level_3="W18X35"),
        braces=dict(level_1="5.75", level_2="4.25", level_3="3.00"),
    )

    metadata = dict(
        plate_a={1: 40.0000, 2: 40.0000, 3: 40.0000},
        plate_b={1: 20.0000, 2: 20.0000, 3: 20.0000},
    )

    lvl_weight = dict(
        level_1=1183.702260 * 1e3 / 4.0,
        level_2=1169.173019 * 1e3 / 4.0,
        level_3=1258.981032 * 1e3 / 4.0,
    )  # lb (only the tributary weight for this frame)

    beam_udls = dict(level_1=74.0, level_2=74.0, level_3=74.0)  # lb/in

    mdl, loadcase = generate_archetype(
        level_elevs,
        sections,
        metadata,
        "brbf_3_iv",
        grav_bm_moment_mod,
        grav_col_moment_mod_interior,
        grav_col_moment_mod_exterior,
        lvl_weight,
        beam_udls,
        no_diaphragm=False,
    )

    return mdl, loadcase


def brbf_6_ii(direction) -> tuple[Model, LoadCase]:
    """
    6 story special buckling restrained braced frame risk category II
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
        ),
        gravity_beams=dict(
            level_1="W16X31",
            level_2="W16X31",
            level_3="W16X31",
            level_4="W16X31",
            level_5="W16X31",
            level_6="W16X31",
        ),
        lateral_cols=dict(
            level_1="W14X145",
            level_2="W14X145",
            level_3="W14X74",
            level_4="W14X74",
            level_5="W14X38",
            level_6="W14X38",
        ),
        lateral_beams=dict(
            level_1="W18X119",
            level_2="W18X119",
            level_3="W18X97",
            level_4="W18X86",
            level_5="W18X86",
            level_6="W18X35",
        ),
        braces=dict(
            level_1="11.00",
            level_2="9.50",
            level_3="9.50",
            level_4="7.00",
            level_5="6.50",
            level_6="3.25",
        ),
    )

    metadata = dict(
        plate_a={
            1: 40.0000,
            2: 40.0000,
            3: 40.0000,
            4: 40.0000,
            5: 40.0000,
            6: 40.0000,
        },
        plate_b={
            1: 20.0000,
            2: 20.0000,
            3: 20.0000,
            4: 20.0000,
            5: 20.0000,
            6: 20.0000,
        },
    )

    lvl_weight = dict(
        level_1=1096.081853 * 1e3 / 2.0,
        level_2=1079.109688 * 1e3 / 2.0,
        level_3=1075.677824 * 1e3 / 2.0,
        level_4=1065.864905 * 1e3 / 2.0,
        level_5=1064.856116 * 1e3 / 2.0,
        level_6=1166.165264 * 1e3 / 2.0,
    )  # lb (only the tributary weight for this frame)

    beam_udls = dict(
        level_1=74.0,
        level_2=74.0,
        level_3=74.0,
        level_4=74.0,
        level_5=74.0,
        level_6=74.0,
    )  # lb/in

    mdl, loadcase = generate_archetype(
        level_elevs,
        sections,
        metadata,
        "brbf_6_ii",
        grav_bm_moment_mod,
        grav_col_moment_mod_interior,
        grav_col_moment_mod_exterior,
        lvl_weight,
        beam_udls,
        no_diaphragm=False,
    )

    return mdl, loadcase


def brbf_6_iv(direction) -> tuple[Model, LoadCase]:
    """
    6 story special buckling restrained braced frame risk category IV
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
        ),
        gravity_beams=dict(
            level_1="W16X31",
            level_2="W16X31",
            level_3="W16X31",
            level_4="W16X31",
            level_5="W16X31",
            level_6="W16X31",
        ),
        lateral_cols=dict(
            level_1="W14X132",
            level_2="W14X132",
            level_3="W14X74",
            level_4="W14X74",
            level_5="W14X53",
            level_6="W14X53",
        ),
        lateral_beams=dict(
            level_1="W18X119",
            level_2="W18X106",
            level_3="W18X97",
            level_4="W18X97",
            level_5="W18X86",
            level_6="W18X35",
        ),
        braces=dict(
            level_1="10.00",
            level_2="9.00",
            level_3="8.00",
            level_4="6.50",
            level_5="5.25",
            level_6="2.75",
        ),
    )

    metadata = dict(
        plate_a={
            1: 40.0000,
            2: 40.0000,
            3: 40.0000,
            4: 40.0000,
            5: 40.0000,
            6: 40.0000,
        },
        plate_b={
            1: 20.0000,
            2: 20.0000,
            3: 20.0000,
            4: 20.0000,
            5: 20.0000,
            6: 20.0000,
        },
    )

    lvl_weight = dict(
        level_1=1100.217793 * 1e3 / 4.0,
        level_2=1087.387568 * 1e3 / 4.0,
        level_3=1094.132234 * 1e3 / 4.0,
        level_4=1072.253663 * 1e3 / 4.0,
        level_5=1068.894564 * 1e3 / 4.0,
        level_6=1161.128275 * 1e3 / 4.0,
    )  # lb (only the tributary weight for this frame)

    beam_udls = dict(
        level_1=74.0,
        level_2=74.0,
        level_3=74.0,
        level_4=74.0,
        level_5=74.0,
        level_6=74.0,
    )  # lb/in

    mdl, loadcase = generate_archetype(
        level_elevs,
        sections,
        metadata,
        "brbf_6_iv",
        grav_bm_moment_mod,
        grav_col_moment_mod_interior,
        grav_col_moment_mod_exterior,
        lvl_weight,
        beam_udls,
        no_diaphragm=False,
    )

    return mdl, loadcase


def brbf_9_ii(direction) -> tuple[Model, LoadCase]:
    """
    9 story special buckling restrained braced frame risk category II
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
            level_1="W14X233",
            level_2="W14X233",
            level_3="W14X145",
            level_4="W14X132",
            level_5="W14X132",
            level_6="W14X68",
            level_7="W14X68",
            level_8="W14X38",
            level_9="W14X38",
        ),
        lateral_beams=dict(
            level_1="W18X130",
            level_2="W18X130",
            level_3="W18X119",
            level_4="W18X119",
            level_5="W18X106",
            level_6="W18X97",
            level_7="W18X86",
            level_8="W18X86",
            level_9="W18X35",
        ),
        braces=dict(
            level_1="12.75",
            level_2="10.75",
            level_3="10.50",
            level_4="9.00",
            level_5="9.00",
            level_6="8.00",
            level_7="7.00",
            level_8="4.50",
            level_9="3.50",
        ),
    )

    metadata = dict(
        plate_a={
            1: 40.0000,
            2: 40.0000,
            3: 40.0000,
            4: 40.0000,
            5: 40.0000,
            6: 40.0000,
            7: 40.0000,
            8: 40.0000,
            9: 40.0000,
        },
        plate_b={
            1: 20.0000,
            2: 20.0000,
            3: 20.0000,
            4: 20.0000,
            5: 20.0000,
            6: 20.0000,
            7: 20.0000,
            8: 20.0000,
            9: 20.0000,
        },
    )

    lvl_weight = dict(
        level_1=1071.380523 * 1e3 / 2.0,
        level_2=1059.055855 * 1e3 / 2.0,
        level_3=1055.487938 * 1e3 / 2.0,
        level_4=1045.467051 * 1e3 / 2.0,
        level_5=1043.961078 * 1e3 / 2.0,
        level_6=1047.906776 * 1e3 / 2.0,
        level_7=1031.833166 * 1e3 / 2.0,
        level_8=1031.961469 * 1e3 / 2.0,
        level_9=1134.016673 * 1e3 / 2.0,
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
        "brbf_9_ii",
        grav_bm_moment_mod,
        grav_col_moment_mod_interior,
        grav_col_moment_mod_exterior,
        lvl_weight,
        beam_udls,
        no_diaphragm=False,
    )

    return mdl, loadcase


def brbf_9_iv(direction) -> tuple[Model, LoadCase]:
    """
    9 story special buckling restrained braced frame risk category IV
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
            level_1="W14X257",
            level_2="W14X257",
            level_3="W14X193",
            level_4="W14X193",
            level_5="W14X132",
            level_6="W14X132",
            level_7="W14X132",
            level_8="W14X132",
            level_9="W14X132",
        ),
        lateral_beams=dict(
            level_1="W18X143",
            level_2="W18X143",
            level_3="W18X130",
            level_4="W18X130",
            level_5="W18X106",
            level_6="W18X106",
            level_7="W18X97",
            level_8="W18X97",
            level_9="W18X60",
        ),
        braces=dict(
            level_1="11.25",
            level_2="10.50",
            level_3="10.00",
            level_4="9.50",
            level_5="9.00",
            level_6="7.50",
            level_7="7.00",
            level_8="4.50",
            level_9="3.00",
        ),
    )

    metadata = dict(
        plate_a={
            1: 40.0000,
            2: 40.0000,
            3: 40.0000,
            4: 40.0000,
            5: 40.0000,
            6: 40.0000,
            7: 40.0000,
            8: 40.0000,
            9: 40.0000,
        },
        plate_b={
            1: 20.0000,
            2: 20.0000,
            3: 20.0000,
            4: 20.0000,
            5: 20.0000,
            6: 20.0000,
            7: 20.0000,
            8: 20.0000,
            9: 20.0000,
        },
    )

    lvl_weight = dict(
        level_1=1090.252498 * 1e3 / 4.0,
        level_2=1072.593363 * 1e3 / 4.0,
        level_3=1063.275406 * 1e3 / 4.0,
        level_4=1059.683349 * 1e3 / 4.0,
        level_5=1053.734217 * 1e3 / 4.0,
        level_6=1053.508300 * 1e3 / 4.0,
        level_7=1039.574863 * 1e3 / 4.0,
        level_8=1039.827748 * 1e3 / 4.0,
        level_9=1133.664003 * 1e3 / 4.0,
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
        "brbf_9_iv",
        grav_bm_moment_mod,
        grav_col_moment_mod_interior,
        grav_col_moment_mod_exterior,
        lvl_weight,
        beam_udls,
        no_diaphragm=False,
    )

    return mdl, loadcase
