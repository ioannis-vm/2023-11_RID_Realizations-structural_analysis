import pandas as pd
import matplotlib.pyplot as plt
from extra.structural_analysis.src.db import DB_Handler

results_base_path = 'extra/structural_analysis/results/'
db_handler = DB_Handler(db_path=f'{results_base_path}/results.sqlite')

idents_df = db_handler.dataframe_identifiers(
    column_names=[
        'archetype',
        'target',
        'pulse',
        'hz',
        'gm',
        'dt',
        'dir',
        'progress_bar',
        'damping',
    ]
)

idents = db_handler.list_identifiers()

df, info, log = db_handler.retrieve_data(idents[50])
assert isinstance(df, pd.DataFrame)  # make sure we got results
df = df.set_index('time')
print(df)


def make_plot():
    fig, ax = plt.subplots()
    for lvl in [f'{x+1}' for x in range(3)]:
        ax.plot(df[('ID', lvl, '1')] * 100.00, linewidth=0.4, label=f'lvl {lvl}')
    ax.grid()
    ax.legend()
    plt.show()
