"""
Run a pushover analysis
"""

import numpy as np
import pandas as pd
from osmg import solver
from osmg.gen.query import ElmQuery
from osmg.common import G_CONST_IMPERIAL
import matplotlib.pyplot as plt
from extra.structural_analysis.src.structural_analysis.archetypes_2d import scbf_9_ii


def main():
    peak_drift = 60.00  # inches
    direction = 'x'

    mdl, loadcase = scbf_9_ii(direction)
    num_levels = len(mdl.levels) - 1
    level_heights = np.diff([level.elevation for level in mdl.levels.values()])

    lvl_nodes = []
    base_node = list(mdl.levels[0].nodes.values())[0]
    lvl_nodes.append(base_node)
    for i in range(num_levels):
        lvl_nodes.append(loadcase.parent_nodes[i + 1])

    # modal analysis (to get the mode shape)

    # fix leaning column
    elmq = ElmQuery(mdl)
    for i in range(num_levels):
        nd = elmq.search_node_lvl(0.00, 0.00, i + 1)
        assert nd is not None
        nd.restraint = [False, False, False, True, True, True]

    modal_analysis = solver.ModalAnalysis(
        mdl, {loadcase.name: loadcase}, num_modes=1
    )
    modal_analysis.settings.store_forces = False
    modal_analysis.settings.store_fiber = False
    modal_analysis.settings.restrict_dof = [False, True, False, True, False, True]
    modal_analysis.run()
    modeshape_lst = []
    for nd in lvl_nodes:
        modeshape_lst.append(
            modal_analysis.results[loadcase.name].node_displacements[nd.uid][0][0]
        )
    modeshape = np.array(modeshape_lst)

    # pushover analysis
    for i in range(num_levels):
        nd = elmq.search_node_lvl(0.00, 0.00, i + 1)
        assert nd is not None
        nd.restraint = [False, False, False, False, False, False]

    # define analysis
    anl = solver.PushoverAnalysis(mdl, {loadcase.name: loadcase})
    anl.settings.store_forces = False
    anl.settings.store_release_force_defo = False
    anl.settings.solver = "SparseSYM"
    anl.settings.restrict_dof = [False, True, False, True, False, True]
    control_node = lvl_nodes[-1]

    anl.run("x", [peak_drift], control_node, 0.10, modeshape=modeshape)

    # from osmg.graphics.postprocessing_3d import show_deformed_shape
    # show_deformed_shape(
    #     anl,
    #     loadcase.name,
    #     anl.results[loadcase.name].n_steps_success - 1,
    #     0.0,
    #     extrude=True,
    #     animation=False,
    # )

    res_df = pd.DataFrame()
    for i_story, node in enumerate(lvl_nodes):
        if i_story == 0:
            continue
        results = np.column_stack(anl.table_pushover_curve(loadcase.name, "x", node))
        if i_story == 1:
            res_df["Vb"] = results[:, 1]
        res_df[f"Level {i_story}"] = results[:, 0]
    res_df.index.name = "Step"

    res_df['Drift 1'] = (res_df['Level 1'] / level_heights[0]) * 100.00
    for i in range(2, num_levels + 1):
        res_df[f'Drift {i}'] = (
            (res_df[f'Level {i}'] - res_df[f'Level {i - 1}']) / level_heights[i - 1]
        ) * 100.00

    total_mass = 0.0
    for lvl_idx in range(num_levels):
        level = mdl.levels[lvl_idx + 1]
        nodes = [n.uid for n in level.nodes.values()]
        for comp in level.components.values():
            nodes.extend([x.uid for x in comp.internal_nodes.values()])
        mass = sum(loadcase.node_mass[x].val[0] for x in nodes)
        mass += loadcase.node_mass[loadcase.parent_nodes[lvl_idx + 1].uid].val[0]
        total_mass += mass

    weight = total_mass * G_CONST_IMPERIAL

    def make_plot():
        fig, ax = plt.subplots()
        for i_story in range(num_levels):
            ax.plot(
                res_df[f"Drift {i_story + 1}"],
                (res_df['Vb'] / weight) * 100.00,
                label=f'Level {i_story + 1}',
                color='black',
                alpha=((i_story + 2.00) / (num_levels + 2.00)),
                linewidth=((i_story + 2.00) / (num_levels + 2.00)) + 1.00,
            )
        ax.legend()
        ax.set(xlabel='Story drift (%)', ylabel='Base shear / Seismic weight (%)')
        ax.grid(which='both', linewidth=0.30)
        plt.show()

    make_plot()


if __name__ == '__main__':
    main()
