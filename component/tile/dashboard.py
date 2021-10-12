from matplotlib import pyplot as plt

from traitlets import directional_link
from ipywidgets import Output
import ipyvuetify as v

import sepal_ui.sepalwidgets as sw
from sepal_ui.scripts.utils import loading_button, switch

import component.parameter as param
from component.scripts import get_mgci_color, human_format, get_output_name
from component.message import cm

__all__ = ["Dashboard"]


def create_avatar(mgci):
    """Creates a circular avatar containing the MGCI value"""
    color = get_mgci_color(mgci)

    overall_mgci_html = v.Html(
        tag="h1", children=["MGCI", v.Html(tag="br"), str(mgci) + "%"]
    )
    return v.Avatar(color=color, size="150", children=[overall_mgci_html])


class Dashboard(v.Card, sw.SepalWidget):
    
    def __init__(self, model, units='sqkm', rsa=True, *args, **kwargs):
        
        """Dashboard tile to calculate and resume the zonal statistics for the 
        vegetation layer by kapos ranges.
        
        Args:
            model (MgciModel): Mgci Model
            units (str): Units to display the results. Available [{}]
            
        """.format(list(param.UNITS.keys()))

        self._metadata = {"mount_id": "dashboard_tile"}
        self.class_ = "pa-2"

        super().__init__(*args, **kwargs)

        self.model = model
        
        if not units in list(param.UNITS.keys()):
            raise Exception(
                f'{units} is not an available unit, only use {list(param.UNITS.keys())}'
            )
        
        self.units = units
        self.rsa = rsa

        title = v.CardTitle(children=[cm.dashboard.title])
        description = v.CardText(children=[cm.dashboard.description])

        question_icon = v.Icon(children=["mdi-help-circle"], small=True)
        
        # widgets
        
        self.w_year = v.TextField(
            label=cm.dashboard.label.year,
            v_model=self.model.year,
            type="string",
        )
        # Create tooltip
        t_year = v.Flex(
            class_="d-flex",
            children=[
                self.w_year,
                sw.Tooltip(
                    question_icon, cm.dashboard.help.year, left=True, max_width=300
                ),
            ],
        )
        
        self.w_use_rsa = v.Switch(
            v_model=self.rsa,
            label=cm.dashboard.label.rsa,
            value=True
        )
        
        t_rsa = v.Flex(
            class_='d-flex', 
            children=[
                sw.Tooltip(
                    self.w_use_rsa, cm.dashboard.help.rsa, right=True, max_width=300
                )
            ]
        )

        # buttons
        self.btn = sw.Btn(cm.dashboard.label.calculate)
        self.download_btn = sw.Btn(
            cm.dashboard.label.download, class_="ml-2", disabled=True
        )

        w_buttons = v.Flex(children=[self.btn, self.download_btn])

        self.alert = sw.Alert()

        self.children = [
            title,
            description,
            t_year,
            t_rsa,
            w_buttons,
            self.alert,
        ]

        # Decorate functions
        self.get_dashboard = loading_button(
            alert=self.alert, button=self.btn, debug=True
        )(self.get_dashboard)

        self.download_results = loading_button(
            alert=self.alert, button=self.download_btn, debug=True
        )(self.download_results)

        self.btn.on_event("click", self.get_dashboard)
        self.download_btn.on_event("click", self.download_results)

        # Let's link the model year with the year widget here.
        directional_link((self.model, "year"), (self.w_year, "v_model"))

    def download_results(self, *args):
        """Write the results on a comma separated values file, or an excel file"""

        # Generate three reports
        reports = self.model.get_report(self.units)
        m49 = get_geoarea(self.model.aoi_model)
        
        report_filenames = [
            f'ER_MTN_GRNCVI_{m49}.xlsx',
            f'ER_MTN_GRNCOV_{m49}.xlsx',
            f'ER_MTN_TOTL_{m49}.xlsx',
        ]
        
        report_folder = get_report_folder(self.model)
        
        for report, report_filename,  in zip(*[reports, report_filenames]):
            
            report.to_excel(
                str(Path(report_folder, report_filename)), 
                sheet_name=output_name, 
                index=False
            )

        self.alert.add_msg(
            f"The reports were successfully exported in {report_folder}", type_="success"
        )

    @switch("disabled", on_widgets=["download_btn"], targets=[False])
    def get_dashboard(self, widget, event, data):
        """Create dashboard"""

        # Remove previusly dashboards
        if self.is_displayed():
            self.children = self.children[:-1][:]
            
        area_type = (
            cm.dashboard.label.rsa_name 
            if self.w_use_rsa.v_model 
            else cm.dashboard.label.plan
        )

        # Calculate regions
        self.alert.add_msg(cm.dashboard.alert.computing.format(area_type))
        
        # Units will depend of the developer. rsa it's an input from user
        self.model.reduce_to_regions(units=self.units, rsa=self.w_use_rsa.v_model)

        self.alert.append_msg(cm.dashboard.alert.rendering)

        # Get overall MGCI widget
        w_overall = Statistics(self.model, self.units)

        # Get individual stats widgets per Kapos classes
        w_individual = [
            Statistics(self.model, self.units, krange=krange)
            for krange, _ in self.model.summary_df.iterrows()
        ]

        statistics = v.Layout(
            class_="d-block",
            children=[w_overall] + w_individual,
            _metadata={"name": "statistics"},
        )

        new_items = self.children + [statistics]

        self.children = new_items
        self.alert.hide()

    def is_displayed(self):
        """Check if there is a previusly displayed dashboard"""

        for chld in self.children:
            if isinstance(chld._metadata, dict):
                if "statistics" in chld._metadata.values():
                    return True

        return False


class Statistics(v.Card):
    
    def __init__(self, model, units, *args, krange=None, **kwargs):
        super().__init__(*args, **kwargs)

        """
        Creates a full layout view with a circular MGC index followed by 
        horizontal bars of land cover area per kapos classes.
        
        Args:
            krange (int): kapos range number (1,2,3,4,5,6)
            area_per_class (dictionary): Dictionary of lu/lc areas 
            units (str): Units to display the results. Available [{}]
            
        """.format(list(param.UNITS.keys()))

        self.class_ = "ma-4"
        self.row = True
        self.model = model
        self.metadata_ = {"name": "statistics"}

        self.output_chart = Output()

        # Create title and description based on the inputs
        title = cm.dashboard.global_.title
        desc = sw.Alert(children=[
            cm.dashboard.global_.desc.format(param.UNITS[units][1])
        ], dense=True).show()

        if krange:
            title = cm.dashboard.individual.title.format(krange)
            desc = eval(f"cm.dashboard.individual.desc.k{krange}")

        self.children = [
            v.CardTitle(children=[title]),
            v.CardText(children=[desc]),
            v.Row(
                children=[
                    v.Col(
                        sm=4,
                        class_="d-flex justify-center",
                        children=[create_avatar(self.model.get_mgci(krange))],
                    ),
                    v.Col(
                        children=[
                            v.Flex(xs12=True, children=[self.output_chart]),
                        ]
                    ),
                ]
            ),
        ]

        self.get_chart(krange)

    def get_chart(self, krange):

        values = (
            self.model.summary_df.loc[krange][param.DISPLAY_CLASSES]
            if krange
            else self.model.summary_df[param.DISPLAY_CLASSES].sum()
        )

        total_area = values.sum()

        norm_values = [area / total_area * 100 for area in values]
        human_values = [f"{human_format(val)}" for val in values]

        # We are doing this assumming that the dict will create the labels in the
        # same order
        labels, colors = zip(
            *[
                (self.model.lulc_classes[class_][0], self.model.lulc_classes[class_][1])
                for class_ in values.to_dict()
            ]
        )

        with self.output_chart:

            plt.style.use("dark_background")

            # create the chart
            fig, ax = plt.subplots(
                figsize=[25, len(values) * 2], facecolor=((0, 0, 0, 0))
            )

            ax.barh(labels, norm_values, color=colors)

            for i, (norm, name, val, color) in enumerate(
                zip(norm_values, labels, human_values, colors)
            ):
                ax.text(norm + 2, i, val, fontsize=40, color=color)

            # cosmetic tuning

            ax.set_xlim(0, 110)
            ax.tick_params(axis="y", which="major", pad=30, labelsize=40, left=False)
            ax.tick_params(axis="x", bottom=False, labelbottom=False)
            ax.set_frame_on(False)
            plt.show()
