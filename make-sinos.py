#!/usr/bin/env python
import os
import math
import argparse
from gi.repository import Ufo


def split_extended_path(extended_path):
    """Return (path, first, last-1) from *extended_path* (e.g.
    /home/foo/bla:0:10)."""
    split = extended_path.split(':')
    path = split[0]
    filenames = sorted([f for f in os.listdir(path)
                        if os.path.isfile(os.path.join(path, f))])

    first = int(split[1]) if len(split) > 1 else 0
    last = int(split[2]) - first if len(split) > 2 else len(filenames) - first
    return (path, first, last)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--projection-dir', metavar='PATH', type=str,
                        default='.')
    parser.add_argument('--output-dir', metavar='PATH', type=str,
                        default='.')
    parser.add_argument('--flat-dir', metavar='PATH', type=str)
    parser.add_argument('--dark-dir', metavar='PATH', type=str)

    args = parser.parse_args()


    pm = Ufo.PluginManager()
    g = Ufo.TaskGraph()

    proj_path, proj_nth, proj_count = split_extended_path(args.projection_dir)
    proj_reader = pm.get_task('reader')
    proj_reader.set_properties(path=proj_path, nth=proj_nth, count=proj_count)

    writer = pm.get_task('writer')
    writer.set_properties(filename='{0}/output-%05i.tif'.format(args.output_dir))

    sinogen = pm.get_task('sino-generator')
    sinogen.set_properties(num_projections=proj_count)

    if args.flat_dir and args.dark_dir:
        # Read flat fields
        flat_path, flat_nth, flat_count = split_extended_path(args.flat_dir)
        flat_reader = pm.get_task('reader')
        flat_reader.set_properties(path=flat_path, nth=flat_nth, count=flat_count)

        flat_avg = pm.get_task('averager')
        flat_avg.set_properties(num_generate=proj_count)

        # Read dark fields
        dark_path, dark_nth, dark_count = split_extended_path(args.dark_dir)
        dark_reader = pm.get_task('reader')
        dark_reader.set_properties(path=dark_path, nth=dark_nth, count=dark_count)

        dark_avg = pm.get_task('averager')
        dark_avg.set_properties(num_generate=proj_count)

        # Setup flat-field correction
        ffc = pm.get_task('flat-field-correction')
        ffc.set_properties(absorption_correction=True)

        g.connect_nodes(dark_reader, dark_avg)
        g.connect_nodes(flat_reader, flat_avg)

        g.connect_nodes_full(dark_avg, ffc, 0)
        g.connect_nodes_full(flat_avg, ffc, 1)
        g.connect_nodes_full(proj_reader, ffc, 2)

        g.connect_nodes(ffc, sinogen)
    else:
        g.connect_nodes(proj_reader, sinogen)

    g.connect_nodes(sinogen, writer)

    # Execute the graph
    sched = Ufo.Scheduler()
    sched.set_task_expansion(False)
    sched.run(g)
